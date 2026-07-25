"""
模拟引擎模块
============
基于 PyTorch 的 GPU/CPU 混合计算模拟引擎。
负责网格初始化、反应-扩散方程迭代、内存管理和历史数据记录。
"""

import torch
import numpy as np
import gc
import psutil
import os

from .models import MODEL_FUNCS
from .config import MODEL_INIT_RANGES


class PatternSimulator:
    """斑图模拟引擎

    在 GPU 或 CPU 上执行反应-扩散方程的迭代计算。

    属性:
        grid_size: 网格尺寸
        use_cuda: 是否使用 CUDA 加速
        device: PyTorch 设备
        hardware_info: 硬件描述字符串
    """

    def __init__(self, grid_size=100, use_cuda=True):
        self.grid_size = grid_size
        self.use_cuda = use_cuda and torch.cuda.is_available()
        self.device = torch.device("cuda" if self.use_cuda else "cpu")
        self.hardware_info = self._detect_hardware()

    # ── 硬件检测 ────────────────────────────────────

    def _detect_hardware(self):
        """检测并返回硬件信息描述"""
        if self.use_cuda:
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "未知GPU"
            return f"GPU: {gpu_name}"
        import platform
        return f"CPU: {platform.processor()}"

    def get_memory_usage(self):
        """获取当前内存使用情况"""
        try:
            proc = psutil.Process(os.getpid())
            sys_mem = psutil.virtual_memory()

            gpu_mem = gpu_cached = 0.0
            if self.use_cuda and torch.cuda.is_available():
                gpu_mem = torch.cuda.memory_allocated() / 1024**2
                gpu_cached = torch.cuda.memory_reserved() / 1024**2

            return {
                'python_memory_mb': round(proc.memory_info().rss / 1024**2, 2),
                'system_total_mb': round(sys_mem.total / 1024**2, 2),
                'system_used_mb': round(sys_mem.used / 1024**2, 2),
                'system_percent': round(sys_mem.percent, 2),
                'gpu_memory_mb': round(gpu_mem, 2),
                'gpu_cached_mb': round(gpu_cached, 2),
            }
        except Exception:
            return {k: 0.0 for k in ['python_memory_mb', 'system_total_mb',
                     'system_used_mb', 'system_percent', 'gpu_memory_mb', 'gpu_cached_mb']}

    # ── 内存管理 ────────────────────────────────────

    def clear_memory(self):
        """清理 Python 和 GPU 内存"""
        try:
            if self.use_cuda:
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            gc.collect()
            return True
        except Exception as e:
            print(f"清理内存出错: {e}")
            return False

    # ── 网格初始化 ──────────────────────────────────

    def initialize_grid(self, model_name="模型1"):
        """根据模型初始化种群密度网格"""
        init = MODEL_INIT_RANGES.get(model_name, {
            "x_range": (0.8, 1.0), "y_range": (0.5, 0.6)
        })
        x_min, x_max = init["x_range"]
        y_min, y_max = init["y_range"]

        x = torch.rand(self.grid_size, self.grid_size, device=self.device) * (x_max - x_min) + x_min
        y = torch.rand(self.grid_size, self.grid_size, device=self.device) * (y_max - y_min) + y_min

        return torch.clamp(x, min=1e-6), torch.clamp(y, min=1e-6)

    # ── 模拟执行 ────────────────────────────────────

    def simulate(self, model_name, params, iterations=1000,
                 init_x_range=(0.1, 1.0), init_y_range=(0.1, 1.0),
                 track_points=None):
        """执行完整模拟，返回最终状态和时间演化数据"""
        model_func = MODEL_FUNCS[model_name]
        x, y = self.initialize_grid(model_name=model_name)
        params_t = torch.tensor(params, device=self.device, dtype=torch.float32)

        evolution = {'center': {'x': [], 'y': []}}
        if track_points:
            for pt in track_points:
                evolution[f"point_{pt['x']}_{pt['y']}"] = {'x': [], 'y': []}

        mem_interval = max(1000, iterations // 10)
        cx = cy = self.grid_size // 2

        for i in range(iterations):
            x_new, y_new = model_func(x, y, params_t)

            # 记录中心点
            evolution['center']['x'].append(x[cx, cy].item())
            evolution['center']['y'].append(y[cx, cy].item())

            # 记录跟踪点
            if track_points:
                for pt in track_points:
                    key = f"point_{pt['x']}_{pt['y']}"
                    if 0 <= pt['x'] < self.grid_size and 0 <= pt['y'] < self.grid_size:
                        evolution[key]['x'].append(x[pt['x'], pt['y']].item())
                        evolution[key]['y'].append(y[pt['x'], pt['y']].item())
                    else:
                        evolution[key]['x'].append(0.0)
                        evolution[key]['y'].append(0.0)

            x, y = torch.clamp(x_new, min=1e-6), torch.clamp(y_new, min=1e-6)

            if i % mem_interval == 0 and i > 0:
                if self.use_cuda:
                    torch.cuda.empty_cache()
                gc.collect()

        return x.cpu().numpy(), y.cpu().numpy(), evolution

    def simulate_with_history(self, model_name, params, iterations=100,
                              init_x_range=(0.1, 1.0), init_y_range=(0.1, 1.0)):
        """执行模拟并保存每帧历史（用于动画）"""
        model_func = MODEL_FUNCS[model_name]
        x, y = self.initialize_grid(model_name=model_name)
        params_t = torch.tensor(params, device=self.device, dtype=torch.float32)

        x_hist, y_hist = [], []

        for _ in range(iterations):
            x_hist.append(x.cpu().numpy())
            y_hist.append(y.cpu().numpy())

            x_new, y_new = model_func(x, y, params_t)
            x, y = torch.clamp(x_new, min=1e-6), torch.clamp(y_new, min=1e-6)

        x_hist.append(x.cpu().numpy())
        y_hist.append(y.cpu().numpy())

        return np.array(x_hist), np.array(y_hist)
