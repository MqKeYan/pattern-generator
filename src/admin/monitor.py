"""系统资源监控 - CPU/内存/GPU/温度/功耗/磁盘/网络采集

- 每 1 秒采样，环形缓冲仅保留最近 metrics_window_seconds（默认 3 分钟）。
- 同时累计自启动以来的峰值汇总，随 stats.json 持久化。
- GPU 依赖 pynvml（NVIDIA 驱动），不可用时自动降级；CPU 温度依赖 WMI，拿不到即为 None。
- GPU 过热越过阈值时触发告警回调（带回滞，降温 5℃ 内不重复告警）。
"""

import os
import threading
import time
from collections import deque
from datetime import datetime

import psutil


class SystemMonitor:
    def __init__(self, logger=None, settings=None, overheat_cb=None):
        self.log = logger
        self.settings = settings or {}
        self.overheat_cb = overheat_cb

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None

        self._ring = deque()  # (timestamp, metrics)
        self._peaks = {
            'cpu_percent_max': 0.0,
            'mem_percent_max': 0.0,
            'gpu_temp_max': 0.0,
            'gpu_mem_used_max_mb': 0.0,
        }
        self._last_disk_io = None
        self._last_net_io = None
        self._last_io_time = None
        self._overheat_active = {}  # gpu index -> bool（回滞状态）
        self._process = psutil.Process()

        # pynvml：非 NVIDIA 环境自动降级
        self._nvml = None
        self._gpu_handles = []
        try:
            import pynvml
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            self._gpu_handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)]
            self._nvml = pynvml
        except Exception:
            self._nvml = None

    # ---------- 生命周期 ----------

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name='monitor', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                metrics = self._sample()
                with self._lock:
                    self._ring.append((time.time(), metrics))
                    window = int(self.settings.get('metrics_window_seconds', 180))
                    cutoff = time.time() - window
                    while self._ring and self._ring[0][0] < cutoff:
                        self._ring.popleft()
                    self._update_peaks(metrics)
                self._check_overheat(metrics)
            except Exception as e:
                if self.log:
                    self.log.error(f'监控采样失败: {e!r}')
            self._stop.wait(1)

    # ---------- 采集 ----------

    def _gpu_stats(self):
        stats = []
        if self._nvml is None:
            return stats
        for i, handle in enumerate(self._gpu_handles):
            try:
                mem = self._nvml.nvmlDeviceGetMemoryInfo(handle)
                util = self._nvml.nvmlDeviceGetUtilizationRates(handle)
                temp = self._nvml.nvmlDeviceGetTemperature(handle, self._nvml.NVML_TEMPERATURE_GPU)
                try:
                    power = self._nvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
                except Exception:
                    power = None
                try:
                    power_limit = self._nvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000.0
                except Exception:
                    power_limit = None
                stats.append({
                    'index': i,
                    'name': self._nvml.nvmlDeviceGetName(handle) or f'GPU{i}',
                    'util_percent': int(util.gpu),
                    'mem_used_mb': round(mem.used / 1024 / 1024, 1),
                    'mem_total_mb': round(mem.total / 1024 / 1024, 1),
                    'temp': temp,
                    'power_w': round(power, 1) if power is not None else None,
                    'power_limit_w': round(power_limit, 1) if power_limit else None,
                })
            except Exception:
                continue
        return stats

    def _sample(self):
        now = time.time()
        cpu_percent = psutil.cpu_percent(interval=None)
        freq = psutil.cpu_freq()
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage('C:' if os.name == 'nt' else '/')

        metrics = {
            'time': datetime.fromtimestamp(now).strftime('%H:%M:%S'),
            'cpu_percent': cpu_percent,
            'cpu_freq_mhz': round(freq.current) if freq else None,
            'mem_total_mb': round(mem.total / 1024 / 1024, 1),
            'mem_used_mb': round(mem.used / 1024 / 1024, 1),
            'mem_percent': mem.percent,
            'swap_percent': swap.percent,
            'gpus': self._gpu_stats(),
            'disk_used_percent': disk.percent,
            'disk_read_mb_s': 0.0,
            'disk_write_mb_s': 0.0,
            'net_sent_mb_s': 0.0,
            'net_recv_mb_s': 0.0,
            'proc_cpu_percent': self._process.cpu_percent(),
            'proc_mem_mb': round(self._process.memory_info().rss / 1024 / 1024, 1),
            'timestamp': now,
        }

        try:
            disk_io = psutil.disk_io_counters()
            net_io = psutil.net_io_counters()
            if self._last_io_time and now - self._last_io_time > 0:
                dt = now - self._last_io_time
                if disk_io and self._last_disk_io:
                    metrics['disk_read_mb_s'] = round(max(0, disk_io.read_bytes - self._last_disk_io.read_bytes) / dt / 1024 / 1024, 2)
                    metrics['disk_write_mb_s'] = round(max(0, disk_io.write_bytes - self._last_disk_io.write_bytes) / dt / 1024 / 1024, 2)
                if self._last_net_io:
                    metrics['net_sent_mb_s'] = round(max(0, net_io.bytes_sent - self._last_net_io.bytes_sent) / dt / 1024 / 1024, 2)
                    metrics['net_recv_mb_s'] = round(max(0, net_io.bytes_recv - self._last_net_io.bytes_recv) / dt / 1024 / 1024, 2)
            self._last_disk_io, self._last_net_io, self._last_io_time = disk_io, net_io, now
        except Exception:
            pass

        return metrics

    def _update_peaks(self, metrics):
        self._peaks['cpu_percent_max'] = max(self._peaks['cpu_percent_max'], metrics['cpu_percent'])
        self._peaks['mem_percent_max'] = max(self._peaks['mem_percent_max'], metrics['mem_percent'])
        for gpu in metrics['gpus']:
            if gpu.get('temp') is not None:
                self._peaks['gpu_temp_max'] = max(self._peaks['gpu_temp_max'], gpu['temp'])
            self._peaks['gpu_mem_used_max_mb'] = max(self._peaks['gpu_mem_used_max_mb'], gpu['mem_used_mb'])

    def _check_overheat(self, metrics):
        threshold = int(self.settings.get('notifications', {}).get('gpu_temp_threshold', 85))
        for gpu in metrics['gpus']:
            temp = gpu.get('temp')
            if temp is None:
                continue
            idx = gpu['index']
            if temp >= threshold and not self._overheat_active.get(idx):
                self._overheat_active[idx] = True
                if self.overheat_cb:
                    try:
                        self.overheat_cb(gpu, threshold)
                    except Exception:
                        pass
            elif temp < threshold - 5:
                self._overheat_active[idx] = False

    # ---------- 查询 ----------

    def get_metrics(self):
        """最新一次采样（无 GPU 时 gpus 为空列表）"""
        with self._lock:
            return self._ring[-1][1] if self._ring else self._sample_once_safe()

    def _sample_once_safe(self):
        try:
            return self._sample()
        except Exception:
            return {'time': '', 'gpus': []}

    def get_history(self):
        with self._lock:
            return [m for _, m in self._ring]

    def get_peaks(self):
        with self._lock:
            return dict(self._peaks)

    def set_peaks(self, peaks):
        """stats.json 恢复峰值汇总"""
        if isinstance(peaks, dict):
            with self._lock:
                for key in self._peaks:
                    if key in peaks:
                        self._peaks[key] = peaks[key]

    # ---------- GPU 调度支持 ----------

    @property
    def gpu_count(self):
        return len(self._gpu_handles)

    def gpu_free_mb(self, index):
        if self._nvml is None or index >= len(self._gpu_handles):
            return None
        try:
            mem = self._nvml.nvmlDeviceGetMemoryInfo(self._gpu_handles[index])
            return mem.free / 1024 / 1024
        except Exception:
            return None

    def pick_best_gpu(self):
        """按空闲显存选择最优 GPU，失败返回 0"""
        best, best_free = 0, -1.0
        for i in range(self.gpu_count):
            free = self.gpu_free_mb(i)
            if free is not None and free > best_free:
                best, best_free = i, free
        return best
