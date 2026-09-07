"""模拟引擎 - 执行二维斑图模拟计算

支持可中断计算（cancel_event）、进度回调（progress_cb）、指定 GPU 设备（device_id）。
"""

import torch
import numpy as np
import gc
import psutil
import os
from core.models import MODEL_FUNCS
from core.config import MODEL_INIT_RANGES, GRID_SIZE


class SimulationCancelled(Exception):
    """模拟被用户或管理员取消时抛出"""
    pass


def estimate_vram_mb(grid_size=GRID_SIZE):
    """估算单任务显存需求（MB）：CUDA 上下文基础项 + 运行张量（含安全系数）"""
    tensor_mb = grid_size * grid_size * 4 * 12 * 2 / (1024 * 1024)
    return int(500 + tensor_mb + 1)


def estimate_host_ram_mb(frames, grid_size=GRID_SIZE):
    """估算动画任务的主机内存需求（MB）：x/y 两份全帧历史"""
    return int(frames * grid_size * grid_size * 8 / (1024 * 1024) + 1)


class PatternSimulator:
    """斑图模拟器 - 负责执行二维斑图的演化计算"""

    def __init__(self, grid_size=100, use_cuda=True):
        self.grid_size = grid_size
        self.use_cuda = use_cuda and torch.cuda.is_available()
        self.device = torch.device("cuda" if self.use_cuda else "cpu")
        self.hardware_info = self.get_hardware_info()

    def get_hardware_info(self):
        """获取硬件信息"""
        if self.use_cuda:
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "未知GPU"
            return f"GPU: {gpu_name}"
        else:
            import platform
            cpu_info = self._get_cpu_name() or platform.processor()
            return f"CPU: {cpu_info}"

    @staticmethod
    def _get_cpu_name():
        """获取 CPU 型号名（如 AMD Ryzen 7 5800H），失败时返回 None"""
        import platform
        try:
            if platform.system() == 'Windows':
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                    name, _ = winreg.QueryValueEx(key, 'ProcessorNameString')
                    return str(name).strip() or None
            if platform.system() == 'Linux':
                with open('/proc/cpuinfo', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('model name'):
                            return line.split(':', 1)[1].strip() or None
        except OSError:
            pass
        return None

    def get_memory_usage(self):
        """获取内存使用情况"""
        try:
            process = psutil.Process(os.getpid())

            python_memory = process.memory_info().rss / 1024**2  # MB
            system_memory = psutil.virtual_memory()

            gpu_memory = 0.0
            gpu_memory_cached = 0.0

            if self.use_cuda and torch.cuda.is_available():
                gpu_memory = torch.cuda.memory_allocated() / 1024**2  # MB
                gpu_memory_cached = torch.cuda.memory_reserved() / 1024**2  # MB

            return {
                'python_memory_mb': round(python_memory, 2),
                'system_total_mb': round(system_memory.total / 1024**2, 2),
                'system_used_mb': round(system_memory.used / 1024**2, 2),
                'system_percent': round(system_memory.percent, 2),
                'gpu_memory_mb': round(gpu_memory, 2),
                'gpu_cached_mb': round(gpu_memory_cached, 2)
            }
        except Exception:
            return {
                'python_memory_mb': 0.0,
                'system_total_mb': 0.0,
                'system_used_mb': 0.0,
                'system_percent': 0.0,
                'gpu_memory_mb': 0.0,
                'gpu_cached_mb': 0.0
            }

    def clear_memory(self):
        """清理内存和显存"""
        try:
            if self.use_cuda:
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()

            gc.collect()

            return True

        except Exception as e:
            print(f"清理内存时出错: {e}")
            return False

    def _resolve_device(self, device_id):
        """解析本次任务使用的 torch 设备：未指定时用初始化时的默认设备"""
        if self.use_cuda and device_id is not None:
            return torch.device(f'cuda:{device_id}')
        return self.device

    @staticmethod
    def _check_cancel(cancel_event):
        """每次迭代边界检查取消标志"""
        if cancel_event is not None and cancel_event.is_set():
            raise SimulationCancelled('任务已被取消')

    def initialize_grid(self, model_name="模型1", x_range=None, y_range=None, device=None):
        """初始化网格"""
        # 使用传入的范围，否则使用模型默认范围
        init_range = MODEL_INIT_RANGES.get(model_name, {
            "x_range": (0.8, 1.0),
            "y_range": (0.5, 0.6)
        })
        x_min, x_max = x_range if x_range else init_range["x_range"]
        y_min, y_max = y_range if y_range else init_range["y_range"]
        dev = device if device is not None else self.device

        # 基础随机初始化
        x = torch.rand(self.grid_size, self.grid_size, device=dev) * (x_max - x_min) + x_min
        y = torch.rand(self.grid_size, self.grid_size, device=dev) * (y_max - y_min) + y_min

        # 保证非负，避免数值问题
        x = torch.clamp(x, min=1e-6)
        y = torch.clamp(y, min=1e-6)

        return x, y

    def simulate(self, model_name, params, iterations=1000, init_x_range=(0.1, 1.0),
                 init_y_range=(0.1, 1.0), track_points=None, cancel_event=None,
                 progress_cb=None, device_id=None):
        """执行模拟，返回最终状态和演化数据

        cancel_event: threading.Event，置位后在下一次迭代边界抛出 SimulationCancelled
        progress_cb:  回调函数，接收 0-100 的整数进度
        device_id:    指定 CUDA 设备编号（多 GPU 调度用），None 时使用默认设备
        """
        import contextlib
        model_func = MODEL_FUNCS[model_name]
        dev = self._resolve_device(device_id)
        device_ctx = (torch.cuda.device(device_id)
                      if (self.use_cuda and device_id is not None) else contextlib.nullcontext())

        with device_ctx:
            # 初始化网格 - 使用用户指定的范围或模型默认值
            default_range = (0.1, 1.0)
            if init_x_range != default_range or init_y_range != default_range:
                x, y = self.initialize_grid(model_name=model_name, x_range=init_x_range, y_range=init_y_range, device=dev)
            else:
                x, y = self.initialize_grid(model_name=model_name, device=dev)

            # 将参数转换为tensor
            params_tensor = torch.tensor(params, device=dev, dtype=torch.float32)

            # 存储时间演化数据
            evolution_data = {
                'center': {'x': [], 'y': []}
            }

            # 如果有自定义跟踪点，初始化它们
            if track_points:
                for point in track_points:
                    point_key = f"point_{point['x']}_{point['y']}"
                    evolution_data[point_key] = {'x': [], 'y': []}

            # 添加内存监控
            memory_check_interval = max(1000, iterations // 10)

            # 迭代计算
            for i in range(iterations):
                self._check_cancel(cancel_event)
                x_new, y_new = model_func(x, y, params_tensor)

                # 记录中心点的时间演化
                center_x = self.grid_size // 2
                center_y = self.grid_size // 2
                evolution_data['center']['x'].append(x[center_x, center_y].item())
                evolution_data['center']['y'].append(y[center_x, center_y].item())

                # 记录自定义点的时间演化
                if track_points:
                    for point in track_points:
                        point_key = f"point_{point['x']}_{point['y']}"
                        if 0 <= point['x'] < self.grid_size and 0 <= point['y'] < self.grid_size:
                            evolution_data[point_key]['x'].append(x[point['x'], point['y']].item())
                            evolution_data[point_key]['y'].append(y[point['x'], point['y']].item())
                        else:
                            evolution_data[point_key]['x'].append(0.0)
                            evolution_data[point_key]['y'].append(0.0)

                x, y = x_new, y_new

                # 防止数值溢出
                x = torch.clamp(x, min=1e-6)
                y = torch.clamp(y, min=1e-6)

                # 进度回调
                if progress_cb is not None:
                    progress_cb(round((i + 1) / iterations * 100))

                # 定期清理内存
                if i % memory_check_interval == 0 and i > 0:
                    if self.use_cuda:
                        torch.cuda.empty_cache()
                    gc.collect()

            # 转换为numpy数组用于可视化
            x_np = x.cpu().numpy()
            y_np = y.cpu().numpy()

        return x_np, y_np, evolution_data

    def simulate_with_history(self, model_name, params, iterations=100, start_from=0,
                              init_x_range=(0.1, 1.0), init_y_range=(0.1, 1.0),
                              cancel_event=None, progress_cb=None, device_id=None):
        """执行模拟并保存历史数据（用于动画）

        帧历史存于主机内存（CPU numpy），不占用显存。
        """
        import contextlib
        model_func = MODEL_FUNCS[model_name]
        dev = self._resolve_device(device_id)
        device_ctx = (torch.cuda.device(device_id)
                      if (self.use_cuda and device_id is not None) else contextlib.nullcontext())

        with device_ctx:
            # 每个任务独立初始化网格，避免并发任务读取彼此的随机初始状态。
            default_range = (0.1, 1.0)
            if init_x_range != default_range or init_y_range != default_range:
                x, y = self.initialize_grid(model_name=model_name, x_range=init_x_range, y_range=init_y_range, device=dev)
            else:
                x, y = self.initialize_grid(model_name=model_name, device=dev)

            # 将参数转换为tensor
            params_tensor = torch.tensor(params, device=dev, dtype=torch.float32)

            # 存储历史数据
            x_history = []
            y_history = []

            # 迭代计算，仅保存 start_from 之后的帧
            for i in range(iterations):
                self._check_cancel(cancel_event)
                if i >= start_from:
                    x_history.append(x.cpu().numpy())
                    y_history.append(y.cpu().numpy())

                x_new, y_new = model_func(x, y, params_tensor)
                x, y = x_new, y_new

                # 防止数值溢出
                x = torch.clamp(x, min=1e-6)
                y = torch.clamp(y, min=1e-6)

                # 进度回调
                if progress_cb is not None:
                    progress_cb(round((i + 1) / iterations * 100))

            return np.array(x_history), np.array(y_history)
