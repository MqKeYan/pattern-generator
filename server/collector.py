"""
系统监控采集模块
==============
定时采集 CPU、GPU、内存、Worker 负载数据。
"""
import time
import psutil
import os
import threading
from collections import deque


class SystemCollector:
    """系统监控采集器

    后台线程每秒采集一次系统指标，保留近 10 分钟历史数据。

    用法:
        collector = SystemCollector(pool_manager)
        collector.start()
        history = collector.get_history(minutes=5)
    """

    def __init__(self, pool_manager=None):
        self.pool = pool_manager
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # 历史数据 (最多 600 个点 = 10 分钟)
        self.timestamps = deque(maxlen=600)
        self.cpu = deque(maxlen=600)
        self.gpu = deque(maxlen=600)
        self.gpu_mem = deque(maxlen=600)
        self.sys_mem = deque(maxlen=600)

    def start(self):
        """启动采集线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止采集线程"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        while self._running:
            try:
                self._collect()
            except Exception:
                pass
            time.sleep(1)

    def _collect(self):
        now = time.strftime("%H:%M:%S")
        cpu_pct = psutil.cpu_percent(interval=None)
        cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        sys_mem_total = psutil.virtual_memory().total / 1024 / 1024

        gpu_pct = 0.0
        gpu_mem = 0.0
        try:
            import torch
            if torch.cuda.is_available():
                gpu_pct = torch.cuda.utilization()
                gpu_mem = torch.cuda.memory_allocated() / 1024**2
        except Exception:
            pass

        workers_info = []
        if self.pool:
            workers_info = self.pool.get_workers_status()

        with self._lock:
            self.timestamps.append(now)
            self.cpu.append(cpu_pct)
            self.gpu.append(gpu_pct)
            self.gpu_mem.append(gpu_mem)
            self.sys_mem.append(mem)

        self._current = {
            "timestamp": now,
            "cpu_percent": cpu_pct,
            "cpu_per_core": cpu_per_core,
            "gpu_percent": gpu_pct,
            "gpu_memory_mb": gpu_mem,
            "gpu_memory_total_mb": 8192,
            "system_memory_mb": mem,
            "system_memory_total_mb": sys_mem_total,
            "workers": workers_info,
            "queue_length": len(self.pool.pending_jobs) if self.pool else 0,
        }

    def get_current(self):
        """获取当前瞬时值"""
        return getattr(self, "_current", {})

    def get_history(self, minutes=10):
        """获取近几分钟的历史数据"""
        max_points = minutes * 60
        with self._lock:
            n = min(len(self.timestamps), max_points)
            return {
                "timestamps": list(self.timestamps)[-n:],
                "cpu": list(self.cpu)[-n:],
                "gpu": list(self.gpu)[-n:],
                "memory_mb": list(self.sys_mem)[-n:],
            }
