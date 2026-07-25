"""
系统监控采集模块
==============
定时采集进程级 CPU、GPU、内存、磁盘、任务统计数据。
CPU/GPU 温度优先通过传感器获取，不可用时返回 None。
"""
import time
import os
import subprocess
import threading
from collections import deque

import psutil
import torch


class SystemCollector:
    """系统监控采集器

    后台线程每秒采集一次进程级指标，保留近 10 分钟历史数据。
    """

    def __init__(self, pool_manager=None):
        self.pool = pool_manager
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._proc = psutil.Process(os.getpid())
        self._disk_scan_counter = 0
        self._cached_work_disk = 0

        # 历史数据 (最多 600 个点 = 10 分钟)
        self.timestamps = deque(maxlen=600)
        self.cpu = deque(maxlen=600)
        self.cpu_temp = deque(maxlen=600)
        self.gpu = deque(maxlen=600)
        self.gpu_temp = deque(maxlen=600)
        self.sys_mem = deque(maxlen=600)
        self.disk_used = deque(maxlen=600)

    def start(self):
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        self._proc = psutil.Process(os.getpid())
        # 预热 CPU 采样
        self._proc.cpu_percent()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
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

    # ── 温度检测 ──────────────────────────────────────

    def _cpu_temp(self):
        """CPU 温度，优先 psutil sensors，其次 WMI"""
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    for e in entries:
                        if e.current and e.current > 0:
                            return round(e.current)
        except Exception:
            pass
        # WMI 备用
        try:
            result = subprocess.run(
                ["wmic", "/namespace:\\\\root\\wmi", "PATH",
                 "MSAcpi_ThermalZoneTemperature", "get", "CurrentTemperature"],
                capture_output=True, text=True, timeout=3,
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            for line in lines:
                try:
                    val = int(line)
                    # WMI 返回的是 10×开尔文，转为摄氏度
                    return round(val / 10 - 273.15)
                except ValueError:
                    pass
        except Exception:
            pass
        return None

    def _gpu_temp(self):
        """GPU 温度，通过 nvidia-smi"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split("\n")[0])
        except Exception:
            pass
        return None

    def _work_disk_usage_mb(self):
        """软件自身磁盘占用 (MB) — 扫描 temp 目录"""
        total = 0
        temp_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp"
        )
        if os.path.isdir(temp_dir):
            try:
                for dirpath, dirnames, filenames in os.walk(temp_dir):
                    for f in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, f))
                        except OSError:
                            pass
            except Exception:
                pass
        return round(total / 1024**2, 1)

    # ── 主采集 ────────────────────────────────────────

    def _collect(self):
        now = time.strftime("%H:%M:%S")

        # 进程级 CPU（Win11 风格: 占总 CPU 百分比）
        cpu_pct = self._proc.cpu_percent()
        cpu_temp_val = self._cpu_temp()

        # GPU
        gpu_pct = 0.0
        gpu_mem = 0.0
        gpu_mem_total = 0.0
        try:
            if torch.cuda.is_available():
                gpu_pct = torch.cuda.utilization()
                gpu_mem = torch.cuda.memory_allocated() / 1024**2
                gpu_mem_total = torch.cuda.get_device_properties(0).total_memory / 1024**2
        except Exception:
            pass
        gpu_temp_val = self._gpu_temp()

        # 进程内存 (RSS)
        proc_mem = self._proc.memory_info().rss / 1024 / 1024
        sys_mem_total = psutil.virtual_memory().total / 1024 / 1024
        sys_mem_avail = psutil.virtual_memory().available / 1024 / 1024

        # 磁盘
        disk = psutil.disk_usage(os.getcwd())
        disk_used_gb = disk.used / 1024**3
        disk_total_gb = disk.total / 1024**3
        disk_free_gb = disk.free / 1024**3

        # 软件自身磁盘占用 (每10秒更新一次, 避免频繁IO)
        self._disk_scan_counter += 1
        if self._disk_scan_counter % 10 == 1:
            self._cached_work_disk = self._work_disk_usage_mb()
        work_disk_mb = self._cached_work_disk

        # 任务统计（通过 PoolManager 公开 API）
        jobs_total = 0
        jobs_completed = 0
        jobs_queued = 0
        jobs_failed = 0
        workers_info = []
        queue_len = 0
        if self.pool:
            stats = self.pool.get_job_stats()
            jobs_total = stats["total"]
            jobs_completed = stats["completed"]
            jobs_queued = stats["queued"]
            jobs_failed = stats["failed"]
            workers_info = stats["workers"]
            queue_len = stats["queue_length"]

        # 历史记录
        with self._lock:
            self.timestamps.append(now)
            self.cpu.append(cpu_pct)
            self.cpu_temp.append(cpu_temp_val)
            self.gpu.append(gpu_pct)
            self.gpu_temp.append(gpu_temp_val)
            self.sys_mem.append(proc_mem)
            self.disk_used.append(work_disk_mb)

        self._current = {
            "timestamp": now,
            # CPU
            "cpu_percent": cpu_pct,
            "cpu_temp": cpu_temp_val,
            # GPU
            "gpu_percent": gpu_pct,
            "gpu_temp": gpu_temp_val,
            "gpu_memory_mb": round(gpu_mem, 1),
            "gpu_memory_total_mb": round(gpu_mem_total, 1),
            # 内存
            "system_memory_mb": round(proc_mem, 1),
            "system_memory_total_mb": round(sys_mem_total, 1),
            "system_memory_avail_mb": round(sys_mem_avail, 1),
            # 磁盘
            "disk_used_mb": work_disk_mb,
            "disk_total_gb": round(disk_total_gb, 1),
            "disk_free_gb": round(disk_free_gb, 1),
            # 任务
            "jobs_total": jobs_total,
            "jobs_completed": jobs_completed,
            "jobs_queued": jobs_queued,
            "jobs_failed": jobs_failed,
            # Worker
            "workers": workers_info,
            "queue_length": queue_len,
        }

    def get_current(self):
        return getattr(self, "_current", {})

    def get_history(self, minutes=10):
        max_points = minutes * 60
        with self._lock:
            n = min(len(self.timestamps), max_points)
            return {
                "timestamps": list(self.timestamps)[-n:],
                "cpu": list(self.cpu)[-n:],
                "cpu_temp": list(self.cpu_temp)[-n:],
                "gpu": list(self.gpu)[-n:],
                "gpu_temp": list(self.gpu_temp)[-n:],
                "memory_mb": list(self.sys_mem)[-n:],
                "disk_used_mb": list(self.disk_used)[-n:],
            }
