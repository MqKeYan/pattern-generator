"""系统资源监控 - CPU/内存/GPU/温度/功耗/磁盘/网络采集

- 每 1 秒采样，环形缓冲仅保留最近 metrics_window_seconds（默认 3 分钟）。
- 同时累计自启动以来的峰值汇总，随 stats.json 持久化。
- GPU 计算、专用显存、温度和功耗依赖 pynvml（NVIDIA 驱动），Windows GPU 共享内存与软件进程 GPU 指标通过 DXGI/PDH 读取；CPU 功耗通过 Windows Energy Meter 读取，相关数据不可用时为 None。
- GPU 过热越过阈值时触发告警回调（带回滞，降温 5℃ 内不重复告警）。
"""

import os
import ctypes
import math
import re
import threading
import time
from collections import deque
from datetime import datetime
from ctypes import wintypes
from pathlib import Path

import psutil
from common.config import software_root


class _PdhValueUnion(ctypes.Union):
    _fields_ = [
        ('long_value', ctypes.c_long),
        ('double_value', ctypes.c_double),
        ('large_value', ctypes.c_longlong),
    ]


class _PdhFormattedValue(ctypes.Structure):
    _fields_ = [
        ('status', wintypes.DWORD),
        ('value', _PdhValueUnion),
    ]


def _fallback_cpu_packages():
    """拓扑读取失败时，将全部逻辑处理器归入一个物理 CPU。"""
    count = psutil.cpu_count() or 1
    return [{
        'index': 0,
        'logical_processors': [
            {'index': index, 'group': 0, 'processor': index}
            for index in range(count)
        ],
    }]


def _windows_cpu_packages():
    """读取 Windows 物理处理器封装与逻辑处理器映射。"""
    if os.name != 'nt':
        return _fallback_cpu_packages()

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    get_topology = kernel32.GetLogicalProcessorInformationEx
    get_topology.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    get_topology.restype = wintypes.BOOL
    get_group_count = kernel32.GetActiveProcessorGroupCount
    get_group_count.restype = wintypes.WORD
    get_processor_count = kernel32.GetActiveProcessorCount
    get_processor_count.argtypes = [wintypes.WORD]
    get_processor_count.restype = wintypes.DWORD

    length = wintypes.DWORD()
    get_topology(3, None, ctypes.byref(length))  # RelationProcessorPackage
    if not length.value:
        return _fallback_cpu_packages()
    buffer = ctypes.create_string_buffer(length.value)
    if not get_topology(3, buffer, ctypes.byref(length)):
        return _fallback_cpu_packages()

    group_offsets = {}
    flat_offset = 0
    for group in range(get_group_count()):
        group_offsets[group] = flat_offset
        flat_offset += get_processor_count(group)

    packages = []
    offset = 0
    pointer_size = ctypes.sizeof(ctypes.c_size_t)
    group_affinity_size = pointer_size + 8
    while offset < length.value:
        relationship = wintypes.DWORD.from_buffer_copy(buffer, offset).value
        size = wintypes.DWORD.from_buffer_copy(buffer, offset + 4).value
        if not size:
            break
        if relationship == 3:
            relation_offset = offset + 8
            group_count = wintypes.WORD.from_buffer_copy(buffer, relation_offset + 22).value
            logical_processors = []
            for group_index in range(group_count):
                affinity_offset = relation_offset + 24 + group_index * group_affinity_size
                mask = ctypes.c_size_t.from_buffer_copy(buffer, affinity_offset).value
                group = wintypes.WORD.from_buffer_copy(buffer, affinity_offset + pointer_size).value
                processor = 0
                while mask:
                    if mask & 1:
                        logical_processors.append({
                            'index': group_offsets.get(group, 0) + processor,
                            'group': group,
                            'processor': processor,
                        })
                    mask >>= 1
                    processor += 1
            if logical_processors:
                packages.append({
                    'index': len(packages),
                    'logical_processors': logical_processors,
                })
        offset += size
    return packages or _fallback_cpu_packages()


class _DxgiGuid(ctypes.Structure):
    _fields_ = [
        ('data1', wintypes.DWORD),
        ('data2', wintypes.WORD),
        ('data3', wintypes.WORD),
        ('data4', wintypes.BYTE * 8),
    ]


class _DxgiLuid(ctypes.Structure):
    _fields_ = [
        ('low_part', wintypes.DWORD),
        ('high_part', wintypes.LONG),
    ]


class _DxgiAdapterDesc1(ctypes.Structure):
    _fields_ = [
        ('description', wintypes.WCHAR * 128),
        ('vendor_id', wintypes.UINT),
        ('device_id', wintypes.UINT),
        ('subsys_id', wintypes.UINT),
        ('revision', wintypes.UINT),
        ('dedicated_video_memory', ctypes.c_size_t),
        ('dedicated_system_memory', ctypes.c_size_t),
        ('shared_system_memory', ctypes.c_size_t),
        ('adapter_luid', _DxgiLuid),
        ('flags', wintypes.UINT),
    ]


def _dxgi_luid_key(luid):
    """将 DXGI LUID 转成 GPU 适配器性能计数器使用的键。"""
    return f'luid_0x{luid.high_part & 0xFFFFFFFF:08x}_0x{luid.low_part:08x}'


def _windows_dxgi_adapters():
    """读取 Windows 图形适配器的 LUID 和共享系统内存上限。"""
    if os.name != 'nt':
        return []
    try:
        dxgi = ctypes.WinDLL('dxgi')
        create_factory = dxgi.CreateDXGIFactory1
        create_factory.argtypes = [ctypes.POINTER(_DxgiGuid), ctypes.POINTER(ctypes.c_void_p)]
        create_factory.restype = ctypes.c_long
        iid_factory1 = _DxgiGuid(
            0x770AAE78, 0xF26F, 0x4DBA,
            (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87),
        )
        factory = ctypes.c_void_p()
        if create_factory(ctypes.byref(iid_factory1), ctypes.byref(factory)) != 0:
            return []

        def com_method(pointer, index, restype, *argtypes):
            vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
            return prototype(vtable[index])

        enum_adapters = com_method(factory, 12, ctypes.c_long, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
        release_factory = com_method(factory, 2, ctypes.c_ulong)
        adapters = []
        index = 0
        while True:
            adapter = ctypes.c_void_p()
            if enum_adapters(factory, index, ctypes.byref(adapter)) != 0:
                break
            get_desc = com_method(adapter, 10, ctypes.c_long, ctypes.POINTER(_DxgiAdapterDesc1))
            release_adapter = com_method(adapter, 2, ctypes.c_ulong)
            desc = _DxgiAdapterDesc1()
            if get_desc(adapter, ctypes.byref(desc)) == 0 and not (desc.flags & 0x2):
                adapters.append({
                    'index': len(adapters),
                    'name': desc.description.rstrip('\x00'),
                    'luid': _dxgi_luid_key(desc.adapter_luid),
                    'shared_mem_total_mb': round(desc.shared_system_memory / 1024 / 1024, 1),
                    'dedicated_mem_total_mb': round(desc.dedicated_video_memory / 1024 / 1024, 1),
                })
            release_adapter(adapter)
            index += 1
        release_factory(factory)
        return adapters
    except Exception:
        return []


class _WindowsPdhCounters:
    """通过 Windows PDH 读取系统实时性能计数器。"""

    _PDH_FMT_DOUBLE = 0x00000200
    _PDH_CSTATUS_VALID_DATA = 0x00000000
    _PDH_CSTATUS_NEW_DATA = 0x00000001

    def __init__(self, logical_processors=None, software_drive='C:'):
        if os.name != 'nt':
            raise RuntimeError('Windows PDH 仅支持 Windows')
        self._pdh = ctypes.WinDLL('pdh')
        self._query = wintypes.HANDLE()
        self._pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)]
        self._pdh.PdhOpenQueryW.restype = wintypes.DWORD
        self._pdh.PdhAddEnglishCounterW.argtypes = [wintypes.HANDLE, ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)]
        self._pdh.PdhAddEnglishCounterW.restype = wintypes.DWORD
        self._pdh.PdhRemoveCounter.argtypes = [wintypes.HANDLE]
        self._pdh.PdhRemoveCounter.restype = wintypes.DWORD
        self._pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
        self._pdh.PdhCollectQueryData.restype = wintypes.DWORD
        self._pdh.PdhGetFormattedCounterValue.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_PdhFormattedValue)]
        self._pdh.PdhGetFormattedCounterValue.restype = wintypes.DWORD
        self._pdh.PdhExpandWildCardPathW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        self._pdh.PdhExpandWildCardPathW.restype = wintypes.DWORD
        self._pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]
        self._pdh.PdhCloseQuery.restype = wintypes.DWORD

        status = self._pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query))
        if status != 0:
            raise OSError(f'PdhOpenQueryW failed: 0x{status:08X}')
        self._counters = {}
        self._disk_bindings = {}
        self._gpu_memory_bindings = {}
        self._gpu_process_bindings = {}
        self._gpu_process_counters_available = False
        self._cpu_power_bindings = {}
        self._gpu_adapters = {adapter['luid']: adapter for adapter in _windows_dxgi_adapters()}
        drive = str(software_drive).rstrip('\\/').upper()
        counter_paths = {
            'cpu_freq_mhz': r'\Processor Information(_Total)\Actual Frequency',
            'disk_io_util_percent': fr'\LogicalDisk({drive})\% Disk Time',
            'disk_latency_ms': fr'\LogicalDisk({drive})\Avg. Disk sec/Transfer',
            'disk_queue_length': fr'\LogicalDisk({drive})\Current Disk Queue Length',
            'disk_read_mb_s': fr'\LogicalDisk({drive})\Disk Read Bytes/sec',
            'disk_write_mb_s': fr'\LogicalDisk({drive})\Disk Write Bytes/sec',
        }
        for processor in logical_processors or []:
            key = f"cpu_{processor['index']}_freq_mhz"
            group = processor['group']
            number = processor['processor']
            counter_paths[key] = fr'\Processor Information({group},{number})\Actual Frequency'

        # Energy Meter 的 PKG 实例对应物理 CPU 封装，功率值以毫瓦提供。
        energy_instances = []
        path_length = wintypes.DWORD(0)
        wildcard = r'\Energy Meter(*)\Power'
        status = self._pdh.PdhExpandWildCardPathW(None, wildcard, None, ctypes.byref(path_length), 0)
        if path_length.value:
            expanded = ctypes.create_unicode_buffer(path_length.value)
            status = self._pdh.PdhExpandWildCardPathW(None, wildcard, expanded, ctypes.byref(path_length), 0)
            if status in (0, 0x800007D2):
                for path in expanded[:].split('\x00'):
                    if path:
                        instance = path.rsplit('\\', 1)[0]
                        instance_name = instance.split('(', 1)[-1].split(')', 1)[0]
                        if instance_name.upper().endswith('_PKG'):
                            energy_instances.append(instance)
        for package_index, instance in enumerate(dict.fromkeys(energy_instances)):
            key = f'cpu_{package_index}_power_w'
            counter_paths[key] = f'{instance}\\Power'
            self._cpu_power_bindings[package_index] = key

        gpu_instances = []
        path_length = wintypes.DWORD(0)
        wildcard = r'\GPU Adapter Memory(*)\Shared Usage'
        status = self._pdh.PdhExpandWildCardPathW(None, wildcard, None, ctypes.byref(path_length), 0)
        if path_length.value:
            expanded = ctypes.create_unicode_buffer(path_length.value)
            status = self._pdh.PdhExpandWildCardPathW(None, wildcard, expanded, ctypes.byref(path_length), 0)
            if status in (0, 0x800007D2):
                for path in expanded[:].split('\x00'):
                    if path:
                        gpu_instances.append(path.rsplit('\\', 1)[0])
        for index, instance in enumerate(dict.fromkeys(gpu_instances)):
            self._gpu_memory_bindings[index] = {'instance': instance, 'keys': {}}
            for metric, counter in {
                'shared_mem_used_bytes': 'Shared Usage',
                'dedicated_mem_used_bytes': 'Dedicated Usage',
                'total_committed_bytes': 'Total Committed',
            }.items():
                key = f'gpu_{index}_{metric}'
                counter_paths[key] = f'{instance}\\{counter}'
                self._gpu_memory_bindings[index]['keys'][metric] = key

        for key, path in counter_paths.items():
            handle = wintypes.HANDLE()
            status = self._pdh.PdhAddEnglishCounterW(self._query, path, 0, ctypes.byref(handle))
            if status == 0:
                self._counters[key] = handle

    def _expand_counter_paths(self, wildcard):
        """展开 PDH 通配符路径，适配随时变化的 GPU 进程实例。"""
        path_length = wintypes.DWORD(0)
        self._pdh.PdhExpandWildCardPathW(None, wildcard, None, ctypes.byref(path_length), 0)
        if not path_length.value:
            return []
        expanded = ctypes.create_unicode_buffer(path_length.value)
        status = self._pdh.PdhExpandWildCardPathW(None, wildcard, expanded, ctypes.byref(path_length), 0)
        if status not in (0, 0x800007D2):
            return []
        return [path for path in expanded[:].split('\x00') if path]

    @staticmethod
    def _gpu_process_path_info(path):
        """从 GPU 进程计数器路径中解析 PID 与显卡 LUID。"""
        instance = path.rsplit('\\', 1)[0]
        match = re.search(r'pid_(\d+)_(luid_0x[0-9a-f]+_0x[0-9a-f]+)', instance, re.IGNORECASE)
        if not match:
            return None
        return int(match.group(1)), match.group(2).lower(), instance

    def _sync_gpu_process_counters(self, software_process_ids):
        """同步当前软件进程的 GPU 内存与引擎计数器。"""
        target_pids = {int(pid) for pid in software_process_ids or ()}
        next_bindings = {}
        found_gpu_counters = False

        for metric, counter in {
            'mem_used_mb': 'Dedicated Usage',
            'shared_mem_used_mb': 'Shared Usage',
            'total_graphics_mem_used_mb': 'Total Committed',
        }.items():
            for path in self._expand_counter_paths(fr'\GPU Process Memory(*)\{counter}'):
                info = self._gpu_process_path_info(path)
                if info is None:
                    continue
                found_gpu_counters = True
                pid, luid, instance = info
                if pid not in target_pids:
                    continue
                key = f'proc_gpu_memory_{pid}_{luid}_{metric}'
                next_bindings[key] = {'kind': 'memory', 'metric': metric, 'luid': luid, 'path': path}

        for path in self._expand_counter_paths(r'\GPU Engine(*)\Utilization Percentage'):
            info = self._gpu_process_path_info(path)
            if info is None:
                continue
            found_gpu_counters = True
            pid, luid, instance = info
            if pid not in target_pids:
                continue
            instance_name = instance.split('(', 1)[-1].split(')', 1)[0]
            key = f'proc_gpu_engine_{pid}_{instance_name}'
            next_bindings[key] = {'kind': 'engine', 'luid': luid, 'path': path}

        self._gpu_process_counters_available = self._gpu_process_counters_available or found_gpu_counters
        stale_keys = set(self._gpu_process_bindings) - set(next_bindings)
        for key in stale_keys:
            handle = self._counters.pop(key, None)
            if handle:
                self._pdh.PdhRemoveCounter(handle)

        for key, binding in next_bindings.items():
            if key in self._counters:
                continue
            handle = wintypes.HANDLE()
            if self._pdh.PdhAddEnglishCounterW(self._query, binding['path'], 0, ctypes.byref(handle)) == 0:
                self._counters[key] = handle
        self._gpu_process_bindings = {
            key: binding for key, binding in next_bindings.items() if key in self._counters
        }

    def sample(self, software_process_ids=None):
        self._sync_gpu_process_counters(software_process_ids)
        if not self._counters or self._pdh.PdhCollectQueryData(self._query) != 0:
            return {}
        result = {}
        for key, handle in self._counters.items():
            counter_type = wintypes.DWORD()
            value = _PdhFormattedValue()
            status = self._pdh.PdhGetFormattedCounterValue(
                handle, self._PDH_FMT_DOUBLE, ctypes.byref(counter_type), ctypes.byref(value))
            if status != 0 or value.status not in (self._PDH_CSTATUS_VALID_DATA, self._PDH_CSTATUS_NEW_DATA):
                continue
            number = value.value.double_value
            if math.isfinite(number):
                result[key] = round(number, 3)
        if 'disk_latency_ms' in result:
            result['disk_latency_ms'] = round(result['disk_latency_ms'] * 1000, 3)
        for key in ('disk_read_mb_s', 'disk_write_mb_s'):
            if key in result:
                result[key] = round(result[key] / 1024 / 1024, 2)
        for key in self._cpu_power_bindings.values():
            if key in result:
                result[key] = round(result[key] / 1000, 1)
        if self._gpu_process_counters_available:
            gpu_util_by_luid = {}
            process_gpu = {
                'proc_gpu_mem_used_mb': 0.0,
                'proc_gpu_shared_mem_used_mb': 0.0,
                'proc_gpu_total_graphics_mem_used_mb': 0.0,
            }
            total_graphics_available = False
            for key, binding in self._gpu_process_bindings.items():
                value = result.pop(key, None)
                if value is None:
                    continue
                if binding['kind'] == 'engine':
                    luid = binding['luid']
                    gpu_util_by_luid[luid] = max(gpu_util_by_luid.get(luid, 0.0), value)
                    continue
                metric = f"proc_gpu_{binding['metric']}"
                process_gpu[metric] += value / 1024 / 1024
                if binding['metric'] == 'total_graphics_mem_used_mb':
                    total_graphics_available = True
            if not total_graphics_available:
                process_gpu['proc_gpu_total_graphics_mem_used_mb'] = (
                    process_gpu['proc_gpu_mem_used_mb'] + process_gpu['proc_gpu_shared_mem_used_mb'])
            process_gpu['proc_gpu_util_percent'] = round(sum(
                min(100, max(0, value)) for value in gpu_util_by_luid.values()), 1)
            result.update({key: round(value, 1) for key, value in process_gpu.items()})
        gpu_memory = []
        for index, binding in self._gpu_memory_bindings.items():
            gpu = {
                'index': index,
                'instance': binding['instance'],
                'luid': binding['instance'].split('(', 1)[-1].split(')', 1)[0].rsplit('_phys_', 1)[0],
            }
            for metric, key in binding['keys'].items():
                if key in result:
                    gpu[metric] = round(result[key], 1)
                result.pop(key, None)
            for metric in ('shared_mem_used_bytes', 'dedicated_mem_used_bytes', 'total_committed_bytes'):
                if metric in gpu:
                    gpu[metric.replace('_bytes', '_mb')] = round(gpu.pop(metric) / 1024 / 1024, 1)
            adapter = self._gpu_adapters.get(gpu['luid'].lower())
            if adapter:
                gpu['name'] = adapter['name']
                gpu['shared_mem_total_mb'] = adapter['shared_mem_total_mb']
                gpu['dedicated_mem_total_mb'] = adapter['dedicated_mem_total_mb']
            if gpu.get('shared_mem_used_mb') is not None and gpu.get('shared_mem_total_mb', 0) > 0:
                gpu['shared_mem_used_percent'] = round(
                    gpu['shared_mem_used_mb'] / gpu['shared_mem_total_mb'] * 100, 1)
            gpu_memory.append(gpu)
        if gpu_memory:
            result['gpu_memory'] = gpu_memory
        return result

    def close(self):
        if self._query:
            self._pdh.PdhCloseQuery(self._query)
            self._query = None


class SystemMonitor:
    def __init__(self, logger=None, settings=None, overheat_cb=None):
        self.log = logger
        self.settings = settings or {}
        self.overheat_cb = overheat_cb
        self.alert_cb = None

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
        self._last_net_io = None
        self._last_io_time = None
        self._overheat_active = {}  # gpu index -> bool（回滞状态）
        self._process = psutil.Process()
        software_path = software_root()
        self._software_mount = Path(software_path).anchor or os.path.abspath(os.sep)
        self._cpu_packages = _windows_cpu_packages()
        self._cpu_power_profile = self._cpu_power_axis_profile()
        logical_processors = [
            processor
            for package in self._cpu_packages
            for processor in package['logical_processors']
        ]
        self._pdh_counters = None
        if os.name == 'nt':
            try:
                self._pdh_counters = _WindowsPdhCounters(logical_processors, self._software_mount)
            except Exception:
                self._pdh_counters = None

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
                if self.alert_cb:
                    self.alert_cb(metrics)
            except Exception as e:
                if self.log:
                    self.log.error_event('monitor_sample_failed', detail={'error': repr(e)})
            self._stop.wait(1)
        if self._pdh_counters:
            self._pdh_counters.close()

    # ---------- 采集 ----------

    @staticmethod
    def _gpu_name_key(name):
        return ''.join(char.lower() for char in str(name or '') if char.isalnum())

    def _classify_gpu(self, name, brand=None):
        """根据 NVML 品牌和型号，将 GPU 粗分为游戏卡或计算卡。"""
        compute_brands = {
            getattr(self._nvml, 'NVML_BRAND_TESLA', -1),
            getattr(self._nvml, 'NVML_BRAND_QUADRO', -1),
            getattr(self._nvml, 'NVML_BRAND_QUADRO_RTX', -1),
            getattr(self._nvml, 'NVML_BRAND_GRID', -1),
        }
        gaming_brands = {
            getattr(self._nvml, 'NVML_BRAND_GEFORCE', -1),
            getattr(self._nvml, 'NVML_BRAND_GEFORCE_RTX', -1),
            getattr(self._nvml, 'NVML_BRAND_TITAN', -1),
            getattr(self._nvml, 'NVML_BRAND_TITAN_RTX', -1),
            getattr(self._nvml, 'NVML_BRAND_NVIDIA_VGAMING', -1),
        }
        if brand in compute_brands:
            return '计算卡'
        if brand in gaming_brands:
            return '游戏卡'
        normalized = str(name or '').lower()
        if any(token in normalized for token in ('tesla', 'data center', 'a100', 'h100', 'l40', 'quadro', 'rtx a', 'rtx pro')):
            return '计算卡'
        if any(token in normalized for token in ('geforce', 'titan', 'gaming')):
            return '游戏卡'
        return '未知'

    def _power_axis_profile(self, handle, name, brand):
        """生成 GPU 功耗图的静态上限和动态切换阈值。"""
        power_limit = None
        max_power_limit = None
        try:
            power_limit = self._nvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000.0
        except Exception:
            pass
        try:
            _, max_power_limit = self._nvml.nvmlDeviceGetPowerManagementLimitConstraints(handle)
            max_power_limit /= 1000.0
        except Exception:
            pass

        gpu_type = self._classify_gpu(name, brand)
        base_limit = power_limit or max_power_limit
        margin = {'游戏卡': 1.10, '计算卡': 1.20}.get(gpu_type, 1.0)
        if base_limit is not None:
            static_cap = base_limit * margin
            if max_power_limit is not None:
                static_cap = min(static_cap, max_power_limit)
        else:
            static_cap = {'游戏卡': 300.0, '计算卡': 500.0}.get(gpu_type, 300.0)
        static_cap = round(static_cap, 1) if static_cap is not None else None
        threshold = None
        if static_cap is not None:
            threshold = math.floor(static_cap / 10) * 10
            if threshold >= static_cap:
                threshold -= 10
        return {
            'gpu_type': gpu_type,
            'power_limit_max_w': round(max_power_limit, 1) if max_power_limit is not None else None,
            'power_static_cap_w': static_cap,
            'power_dynamic_threshold_w': threshold,
        }

    @staticmethod
    def _cpu_name():
        """读取 CPU 型号，用于选择 CPU 功耗图的静态上限。"""
        try:
            import winreg
            with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                return str(winreg.QueryValueEx(key, 'ProcessorNameString')[0]).strip()
        except Exception:
            import platform
            return platform.processor() or '未知 CPU'

    @staticmethod
    def _classify_cpu(name):
        """按型号将 CPU 分为移动、桌面与服务器/工作站功耗类别。"""
        normalized = str(name or '').lower()
        if 'xeon' in normalized and re.search(r'\b69\d{2}p\b', normalized):
            return '旗舰服务器/工作站型'
        if any(token in normalized for token in ('epyc', 'xeon', 'threadripper')):
            return '服务器/工作站型'
        if ' hx ' in normalized or re.search(r'\b\d{3,6}hx\b', normalized):
            return '旗舰移动型'
        if re.search(r'\b\d{3,6}(?:hs|h)\b', normalized):
            return '性能移动型'
        if re.search(r'\b\d{3,6}(?:u|p)\b', normalized):
            return '低功耗移动型'
        if (re.search(r'\b(?:core\s+(?:ultra\s+)?i?[579]|i[579])[- ]?\d+[a-z]*(?:k|kf|ks)\b', normalized)
                or re.search(r'\bryzen 9 (?:7950x3d|7950x|9950x3d|9950x)\b', normalized)):
            return '高性能台式型'
        return '桌面型'

    def _cpu_power_axis_profile(self):
        """生成 CPU 功耗图的静态上限和动态切换阈值。"""
        cpu_type = self._classify_cpu(self._cpu_name())
        static_cap = {
            '低功耗移动型': 70.0,
            '性能移动型': 120.0,
            '旗舰移动型': 160.0,
            '桌面型': 180.0,
            '高性能台式型': 260.0,
            '服务器/工作站型': 400.0,
            '旗舰服务器/工作站型': 500.0,
        }[cpu_type]
        threshold = math.floor(static_cap / 10) * 10
        if threshold >= static_cap:
            threshold -= 10
        return {
            'cpu_type': cpu_type,
            'power_static_cap_w': static_cap,
            'power_dynamic_threshold_w': threshold,
        }

    def _match_gpu_memory(self, name, index, gpu_memory):
        """按 DXGI 适配器名称将共享内存计数器匹配到 NVML GPU。"""
        if not gpu_memory:
            return None
        name_key = self._gpu_name_key(name)
        candidates = [item for item in gpu_memory if item.get('name') and self._gpu_name_key(item['name']) == name_key]
        if candidates:
            return candidates[0]
        if len(gpu_memory) == len(self._gpu_handles) and index < len(gpu_memory):
            return gpu_memory[index]
        return None

    @staticmethod
    def _sum_gpu_metric(gpus, key):
        values = [gpu.get(key) for gpu in gpus if gpu.get(key) is not None]
        return round(sum(values), 1) if values else None

    def _gpu_stats(self, pdh_metrics=None):
        stats = []
        if self._nvml is None:
            return stats
        gpu_memory = (pdh_metrics or {}).get('gpu_memory', [])
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
                name = self._nvml.nvmlDeviceGetName(handle) or f'GPU{i}'
                try:
                    brand = self._nvml.nvmlDeviceGetBrand(handle)
                except Exception:
                    brand = None
                power_profile = self._power_axis_profile(handle, name, brand)
                mem_used_mb = round(mem.used / 1024 / 1024, 1)
                mem_total_mb = round(mem.total / 1024 / 1024, 1)
                shared = self._match_gpu_memory(name, i, gpu_memory) or {}
                shared_used_mb = shared.get('shared_mem_used_mb')
                shared_total_mb = shared.get('shared_mem_total_mb')
                total_graphics_mem_used_mb = shared.get('total_committed_mb')
                if total_graphics_mem_used_mb is None and shared_used_mb is not None:
                    total_graphics_mem_used_mb = round(mem_used_mb + shared_used_mb, 1)
                total_graphics_mem_total_mb = None
                if shared_total_mb is not None:
                    total_graphics_mem_total_mb = round(mem_total_mb + shared_total_mb, 1)
                stats.append({
                    'index': i,
                    'name': name,
                    'util_percent': int(util.gpu),
                    'mem_used_mb': mem_used_mb,
                    'mem_total_mb': mem_total_mb,
                    'mem_used_percent': round(mem.used / mem.total * 100, 1) if mem.total else None,
                    'shared_mem_used_mb': shared_used_mb,
                    'shared_mem_total_mb': shared_total_mb,
                    'shared_mem_used_percent': shared.get('shared_mem_used_percent'),
                    'total_graphics_mem_used_mb': total_graphics_mem_used_mb,
                    'total_graphics_mem_total_mb': total_graphics_mem_total_mb,
                    'temp': temp,
                    'power_w': round(power, 1) if power is not None else None,
                    'power_limit_w': round(power_limit, 1) if power_limit else None,
                    **power_profile,
                })
            except Exception:
                continue
        return stats

    def _cpu_stats(self, per_cpu_percent, pdh_metrics):
        """按物理 CPU 聚合逻辑处理器使用率和实时频率。"""
        packages = []
        for package in self._cpu_packages:
            logical = []
            frequencies = []
            usages = []
            for processor in package['logical_processors']:
                index = processor['index']
                usage = per_cpu_percent[index] if index < len(per_cpu_percent) else None
                frequency = pdh_metrics.get(f'cpu_{index}_freq_mhz')
                if usage is not None:
                    usages.append(usage)
                if frequency is not None:
                    frequencies.append(frequency)
                logical.append({
                    **processor,
                    'util_percent': round(usage, 1) if usage is not None else None,
                    'freq_mhz': round(frequency, 1) if frequency is not None else None,
                })
            packages.append({
                'index': package['index'],
                'util_percent': round(sum(usages) / len(usages), 1) if usages else None,
                'freq_mhz': round(sum(frequencies) / len(frequencies), 1) if frequencies else None,
                'power_w': pdh_metrics.get(f"cpu_{package['index']}_power_w"),
                **self._cpu_power_profile,
                'logical_processors': logical,
            })
        return packages

    def _sample(self):
        now = time.time()
        per_cpu_percent = psutil.cpu_percent(interval=None, percpu=True)
        cpu_percent = round(sum(per_cpu_percent) / len(per_cpu_percent), 1) if per_cpu_percent else 0.0
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage(self._software_mount)
        volumes = []
        try:
            for partition in psutil.disk_partitions(all=False):
                if 'cdrom' in (partition.opts or '').lower():
                    continue
                if os.path.normcase(os.path.abspath(partition.mountpoint)) != os.path.normcase(os.path.abspath(self._software_mount)):
                    continue
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                except OSError:
                    continue
                volumes.append({
                    'mountpoint': partition.mountpoint,
                    'used_percent': round(usage.percent, 1),
                    'total_gb': round(usage.total / 1024 / 1024 / 1024, 2),
                    'free_gb': round(usage.free / 1024 / 1024 / 1024, 2),
                })
        except Exception:
            pass
        # 将进程 CPU 使用率换算为整机百分比，与系统 CPU 使用率保持同一口径。
        process_cpu_percent = self._process.cpu_percent()
        usable_cpu_count = max(1, len(self._process.cpu_affinity()))
        process_memory_mb = self._process.memory_info().rss
        software_process_ids = {self._process.pid}
        try:
            for child in self._process.children(recursive=True):
                try:
                    software_process_ids.add(child.pid)
                    process_memory_mb += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        pdh_metrics = self._pdh_counters.sample(software_process_ids) if self._pdh_counters else {}
        cpu_packages = self._cpu_stats(per_cpu_percent, pdh_metrics)
        gpu_stats = self._gpu_stats(pdh_metrics)
        gpu_totals = {}
        if gpu_stats:
            gpu_totals = {
                'gpu_total_util_percent': sum(gpu.get('util_percent', 0) for gpu in gpu_stats),
                'gpu_total_mem_used_mb': sum(gpu.get('mem_used_mb', 0) for gpu in gpu_stats),
                'gpu_total_mem_total_mb': sum(gpu.get('mem_total_mb', 0) for gpu in gpu_stats),
                'gpu_total_shared_mem_used_mb': self._sum_gpu_metric(gpu_stats, 'shared_mem_used_mb'),
                'gpu_total_shared_mem_total_mb': self._sum_gpu_metric(gpu_stats, 'shared_mem_total_mb'),
                'gpu_total_total_graphics_mem_total_mb': self._sum_gpu_metric(gpu_stats, 'total_graphics_mem_total_mb'),
                'gpu_total_power_w': self._sum_gpu_metric(gpu_stats, 'power_w'),
                'gpu_total_power_static_cap_w': self._sum_gpu_metric(gpu_stats, 'power_static_cap_w'),
            }

        metrics = {
            'time': datetime.fromtimestamp(now).strftime('%H:%M:%S'),
            'cpu_percent': cpu_percent,
            'cpu_freq_mhz': pdh_metrics.get('cpu_freq_mhz'),
            'cpus': cpu_packages,
            'disks': [],
            'volumes': volumes,
            'mem_total_mb': round(mem.total / 1024 / 1024, 1),
            'mem_used_mb': round(mem.used / 1024 / 1024, 1),
            'mem_percent': mem.percent,
            'swap_percent': swap.percent,
            'gpus': gpu_stats,
            'disk_used_percent': disk.percent,
            'disk_io_util_percent': pdh_metrics.get('disk_io_util_percent'),
            'disk_latency_ms': pdh_metrics.get('disk_latency_ms'),
            'disk_queue_length': pdh_metrics.get('disk_queue_length'),
            'disk_read_mb_s': pdh_metrics.get('disk_read_mb_s', 0.0),
            'disk_write_mb_s': pdh_metrics.get('disk_write_mb_s', 0.0),
            'net_sent_mb_s': 0.0,
            'net_recv_mb_s': 0.0,
            'net_sent_packets_s': 0.0,
            'net_recv_packets_s': 0.0,
            'proc_cpu_percent': round(process_cpu_percent / usable_cpu_count, 1),
            'proc_mem_mb': round(process_memory_mb / 1024 / 1024, 1),
            'proc_gpu_util_percent': pdh_metrics.get('proc_gpu_util_percent'),
            'proc_gpu_mem_used_mb': pdh_metrics.get('proc_gpu_mem_used_mb'),
            'proc_gpu_shared_mem_used_mb': pdh_metrics.get('proc_gpu_shared_mem_used_mb'),
            'proc_gpu_total_graphics_mem_used_mb': pdh_metrics.get('proc_gpu_total_graphics_mem_used_mb'),
            'timestamp': now,
        }
        metrics.update(gpu_totals)

        try:
            net_io = psutil.net_io_counters()
            if self._last_io_time and now - self._last_io_time > 0:
                dt = now - self._last_io_time
                if self._last_net_io:
                    metrics['net_sent_mb_s'] = round(max(0, net_io.bytes_sent - self._last_net_io.bytes_sent) / dt / 1024 / 1024, 2)
                    metrics['net_recv_mb_s'] = round(max(0, net_io.bytes_recv - self._last_net_io.bytes_recv) / dt / 1024 / 1024, 2)
                    metrics['net_sent_packets_s'] = round(max(0, net_io.packets_sent - self._last_net_io.packets_sent) / dt, 1)
                    metrics['net_recv_packets_s'] = round(max(0, net_io.packets_recv - self._last_net_io.packets_recv) / dt, 1)
            self._last_net_io, self._last_io_time = net_io, now
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
