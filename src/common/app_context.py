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
from pathlib import Path

from core.config import GRID_SIZE, MODEL_CONFIGS, MODEL_INIT_RANGES, PARAM_NAMES, MODEL_DISPLAY_NAMES
from core.simulation import PatternSimulator, SimulationCancelled
from core.task_worker import execute_isolated_task
from common.config import load_settings, VERSION
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

    def unregister(self, client_id, session_id, websocket=None):
        with self._lock:
            sessions = self._items.get(client_id)
            if not sessions:
                return 'missing'
            key = session_id or client_id
            current = sessions.get(key)
            if current is None:
                return 'missing'
            if websocket is not None and current[0] is not websocket:
                return 'replaced'
            sessions.pop(key, None)
            if not sessions:
                self._items.pop(client_id, None)
            return 'removed'

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
monitor = SystemMonitor(logger=log, settings=settings)
clients = ClientManager(logger=log, settings=settings)
access = AccessControl(logger=log)
notifier = NotificationManager(logger=log, settings=settings)
monitor.alert_cb = notifier.check_metrics
presence_sockets = PresenceSockets()
client_cache = ResultStore(settings=settings, logger=log)


def persist_task_result(task, result):
    """任务完成后立即将结果转存磁盘，避免大型图表常驻任务内存。"""
    if not task.client_id or not isinstance(result, dict):
        return False
    if task.type == 'simulate':
        return client_cache.put(task.client_id, task.task_id, 'simulation', {
            'type': 'simulation',
            'viz_2d': result.get('viz_2d'),
            'viz_3d': result.get('viz_3d'),
            'model': result.get('model'),
            'iterations': result.get('iterations'),
        })
    if task.type == 'animate':
        return client_cache.put(task.client_id, task.task_id, 'animation', {
            'type': 'animation',
            'animation': result.get('animation'),
            'model': result.get('model'),
            'start_iteration': result.get('start_iteration'),
        })
    return False


def release_runtime_memory():
    """回收已无引用的任务对象与 CUDA 缓存，不强制压缩进程工作集。"""
    summary = {'gc_collected': gc.collect(), 'cuda_cache_released': False}
    if use_cuda:
        try:
            torch = __import__('torch')
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            summary['cuda_cache_released'] = True
        except Exception:
            pass
    return summary


def execute_task(task):
    """任务队列的工作函数：在独立子进程中执行计算。"""
    try:
        payload = dict(task.payload)
        payload.pop('client_notifications', None)
        return execute_isolated_task(
            payload,
            task.gpu_id,
            task.cancel_event.is_set,
            task.set_progress,
        )
    except SimulationCancelled as e:
        raise TaskCancelled(str(e)) from e


task_queue = TaskQueue(logger=log, settings=settings, clients=clients,
                       monitor=monitor, notifier=notifier, task_fn=execute_task,
                       result_persist=persist_task_result,
                       result_release=release_runtime_memory)


def asset_version(*paths):
    """用静态资源修改时间生成缓存版本，避免样式更新被旧缓存遮蔽"""
    if not paths:
        base_path = os.path.dirname(os.path.dirname(__file__))
        paths = (
            os.path.join(base_path, 'web', 'static'),
            os.path.join(base_path, 'admin', 'static'),
        )
    try:
        files = []
        for path in paths:
            item = Path(path)
            files.extend(sorted(entry for entry in item.rglob('*') if entry.is_file()) if item.is_dir() else [item])
        return '.'.join(str(int(os.path.getmtime(path))) for path in files)
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
