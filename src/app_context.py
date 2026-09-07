"""组合根 - 全局单例与任务执行函数

主服务（web/server.py）与后台服务（admin/server.py）共享的运行时上下文。
settings 为共享 dict：后台修改设置后调用 reload_runtime_settings() 原地更新，
所有持有引用的模块（TaskQueue、Monitor 等）即刻看到新值。
"""

import asyncio
import gc
import os
import re
import threading

from core.config import GRID_SIZE, MODEL_CONFIGS, MODEL_INIT_RANGES, PARAM_NAMES, MODEL_DISPLAY_NAMES
from core.simulation import PatternSimulator, SimulationCancelled
from core.visualization import PatternVisualizer
from settings import load_settings
from version import VERSION
from admin.logger import get_logger
from admin.monitor import SystemMonitor
from admin.clients import ClientManager
from admin.access_control import AccessControl
from admin.tasks import TaskCancelled, TaskQueue
from admin.notifications import NotificationManager
from admin.result_store import ResultStore

log = get_logger()
settings = load_settings()


class PresenceSockets:
    """前台客户端页面连接注册表：client_id -> {session_id: (ws, 事件循环)}。

    后台删除/踢出客户端时跨线程调度关闭其页面 WebSocket
    （ws.close 必须在连接所属的事件循环中执行）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}
        self._pending = 0

    def reserve(self, max_connections):
        """为握手保留连接名额，防止未认证连接耗尽服务资源。"""
        with self._lock:
            total = sum(len(sessions) for sessions in self._items.values())
            if total + self._pending >= max_connections:
                return False
            self._pending += 1
            return True

    def release_reservation(self):
        with self._lock:
            self._pending = max(0, self._pending - 1)

    def register(self, client_id, session_id, ws, max_per_client):
        """登记已认证连接，同一客户端会话数达到上限时拒绝。"""
        loop = asyncio.get_running_loop()
        with self._lock:
            sessions = self._items.setdefault(client_id, {})
            key = session_id or client_id
            if key not in sessions and len(sessions) >= max_per_client:
                if not sessions:
                    self._items.pop(client_id, None)
                return False
            sessions[key] = (ws, loop)
            return True

    def unregister(self, client_id, session_id):
        with self._lock:
            sessions = self._items.get(client_id)
            if sessions:
                sessions.pop(session_id or client_id, None)
                if not sessions:
                    self._items.pop(client_id, None)

    def close_all(self, client_id, code=4001):
        """关闭该客户端的全部页面连接，返回成功调度的关闭数量"""
        with self._lock:
            sessions = self._items.pop(client_id, {})
        closed = 0
        for ws, loop in sessions.values():
            try:
                asyncio.run_coroutine_threadsafe(ws.close(code=code), loop)
                closed += 1
            except Exception:
                pass
        return closed


def reload_runtime_settings():
    """原地刷新共享 settings（后台保存设置后调用）"""
    settings.clear()
    settings.update(load_settings())


def cpu_model():
    """CPU 型号：优先读注册表 ProcessorNameString，失败回退 platform；
    英特尔名称规范化为“Intel Core i7-12700K”形式，AMD 去掉末尾
    “N-Core Processor”核心数后缀，只保留型号主体"""
    import platform
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            name = str(winreg.QueryValueEx(key, 'ProcessorNameString')[0]).strip()
    except Exception:
        name = platform.processor() or '未知'
    if 'intel' in name.lower():
        # 去掉 (R)/(TM) 注册商标、代际前缀（如“12th Gen”）与“CPU @ 频率”尾缀
        name = re.sub(r'\(R\)|\(TM\)|\(C\)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'^\s*\d+(?:th|st|nd|rd)\s+gen\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+cpu\s+@.*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+', ' ', name).strip()
    return re.sub(r'\s+\d+[- ]?core\s+(processor|cpu)$', '', name, flags=re.IGNORECASE).strip()


def service_info():
    """服务信息字典：主界面信息卡片与后台管理中心共用"""
    import platform
    import torch
    return {
        'python': platform.python_version(),
        # PyTorch 版本去掉 +cu132 等本地构建后缀，只保留本体版本号
        'torch': torch.__version__.split('+', 1)[0],
        'cuda': torch.version.cuda if torch.cuda.is_available() else None,
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'cpu': cpu_model(),
        'hardware': 'GPU' if torch.cuda.is_available() else 'CPU',
    }


use_cuda = __import__('torch').cuda.is_available()
simulator = PatternSimulator(grid_size=GRID_SIZE, use_cuda=use_cuda)
visualizer = PatternVisualizer()
monitor = SystemMonitor(logger=log, settings=settings)
clients = ClientManager(logger=log, settings=settings)
access = AccessControl(logger=log)
notifier = NotificationManager(logger=log, settings=settings)
presence_sockets = PresenceSockets()
client_cache = ResultStore(settings=settings, logger=log)


def execute_task(task):
    """任务队列的工作函数：执行模拟/动画并生成可视化数据（在线程池中运行）"""
    payload = task.payload
    model = payload['model']
    params = payload['params']
    device_id = task.gpu_id
    cancel_event = task.cancel_event

    def progress_cb(p):
        task.set_progress(p)

    try:
        if task.type == 'simulate':
            x_data, y_data, evolution_data = simulator.simulate(
                model, params, payload['iterations'],
                init_x_range=payload['init_x_range'], init_y_range=payload['init_y_range'],
                track_points=payload.get('track_points'),
                cancel_event=cancel_event, progress_cb=progress_cb, device_id=device_id,
            )
            viz_2d = visualizer.create_comprehensive_plot(
                x_data, y_data, evolution_data, payload.get('track_points'), model, lang=payload.get('lang', 'zh-CN'))
            viz_3d = visualizer.create_3d_pattern(x_data, model, lang=payload.get('lang', 'zh-CN'))
            return {'viz_2d': viz_2d, 'viz_3d': viz_3d, 'model': model, 'iterations': payload['iterations']}

        if task.type == 'animate':
            total_iterations = payload['frames'] + payload['start_frame']
            x_history, y_history = simulator.simulate_with_history(
                model, params, total_iterations, start_from=payload['start_frame'],
                init_x_range=payload['init_x_range'], init_y_range=payload['init_y_range'],
                cancel_event=cancel_event, progress_cb=progress_cb, device_id=device_id,
            )
            anim = visualizer.create_animation_frames(x_history, y_history, start_iteration=payload['start_frame'])
            return {'animation': anim, 'model': model, 'start_iteration': payload['start_frame']}

        raise ValueError(f'未知任务类型: {task.type}')
    except SimulationCancelled as e:
        raise TaskCancelled(str(e)) from e
    finally:
        gc.collect()
        if use_cuda:
            __import__('torch').cuda.empty_cache()


task_queue = TaskQueue(logger=log, settings=settings, clients=clients,
                       monitor=monitor, notifier=notifier, task_fn=execute_task)


def asset_version(*paths):
    """用静态资源修改时间生成缓存版本，避免样式更新被旧缓存遮蔽"""
    if not paths:
        base_path = os.path.dirname(__file__)
        paths = (
            os.path.join(base_path, 'web', 'static', 'css', 'style.css'),
            os.path.join(base_path, 'web', 'static', 'js', 'i18n.js'),
            os.path.join(base_path, 'web', 'static', 'js', 'app.js'),
        )
    try:
        return '.'.join(str(int(os.path.getmtime(path))) for path in paths)
    except OSError:
        return VERSION


def init_config():
    """主页面内联配置（不含 settings，防敏感字段泄漏）"""
    return {
        'version': VERSION,
        'models': MODEL_CONFIGS,
        'init_ranges': MODEL_INIT_RANGES,
        'param_names': PARAM_NAMES,
        'display_names': MODEL_DISPLAY_NAMES,
        'grid_size': GRID_SIZE,
        'hardware_info': simulator.hardware_info,
        'service_info': service_info(),
        'asset_ver': asset_version(),
    }
