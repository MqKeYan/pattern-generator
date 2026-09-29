"""External interpreter discovery and cached per-engine operation probes (stdlib only)."""
import copy
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading

ENGINE_NAMES = {'pytorch': 'PyTorch', 'cupy': 'CuPy', 'warp': 'NVIDIA Warp',
                'taichi': 'Taichi', 'pyopencl': 'PyOpenCL',
                'numba': 'Numba', 'numpy': 'NumPy'}
PRIORITY = tuple(ENGINE_NAMES)
PROTOCOL = 1


def worker_entry():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'compute_worker' / 'core' / 'external_worker.py'
    return Path(__file__).resolve().parents[1] / 'core' / 'external_worker.py'


def child_env():
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', '_MEIPASS2'):
        env.pop(key, None)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    cache_root = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'pattern-generator' / 'compute-cache'
    env.setdefault('NUMBA_CACHE_DIR', str(cache_root / 'numba'))
    env.setdefault('WARP_CACHE_PATH', str(cache_root / 'warp'))
    env.setdefault('TAICHI_CACHE_DIR', str(cache_root / 'taichi'))
    env.setdefault('PYOPENCL_CACHE_DIR', str(cache_root / 'pyopencl'))
    # Prevent the frozen bootloader's DLL path from contaminating external Python.
    return env


def popen(args, **kwargs):
    # On Windows PyInstaller adjusts the process DLL search path. Clear it only
    # while creating the external process and restore it immediately afterwards.
    with _spawn_lock:
        if sys.platform == 'win32' and getattr(sys, 'frozen', False):
            import ctypes
            buffer = ctypes.create_unicode_buffer(32768)
            ctypes.windll.kernel32.GetDllDirectoryW(len(buffer), buffer)
            ctypes.windll.kernel32.SetDllDirectoryW(None)
            try:
                return subprocess.Popen(args, env=child_env(),
                                        creationflags=subprocess.CREATE_NO_WINDOW, **kwargs)
            finally:
                ctypes.windll.kernel32.SetDllDirectoryW(buffer.value or None)
        return subprocess.Popen(args, env=child_env(),
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), **kwargs)


_spawn_lock = threading.Lock()


def run_capture(args, timeout=10):
    process = popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', errors='replace')
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise ValueError('Python/engine probe timed out')
    if process.returncode:
        raise ValueError((err or out or 'Python process failed')[-2000:])
    return out


def inspect_python(candidate):
    path = Path(candidate)
    if not path.is_absolute() or not path.is_file() or 'windowsapps' in str(path).lower():
        raise ValueError('Select an existing absolute Python executable path')
    data = json.loads(run_capture([str(path), '-c',
        'import json,sys,struct;print(json.dumps(dict(path=sys.executable,version=list(sys.version_info[:3]),bits=struct.calcsize("P")*8)))']))
    if tuple(data['version'][:2]) < (3, 13) or data['bits'] != 64:
        raise ValueError('Requires 64-bit Python 3.13 or newer')
    return data


def resolve_python(configured='auto'):
    if configured != 'auto':
        candidates = [configured]
    else:
        candidates = []
        # Source runs honor the interpreter used to launch the application.
        if not getattr(sys, 'frozen', False):
            return inspect_python(sys.executable)
        default = shutil.which('python')
        if default:
            try:
                return inspect_python(default)
            except (OSError, ValueError, KeyError, TypeError):
                candidates.append(default)
        launcher = shutil.which('py')
        if launcher:
            try:
                candidates.append(run_capture([launcher, '-3', '-c', 'import sys;print(sys.executable)']).strip())
            except (OSError, ValueError):
                pass
        if sys.platform == 'win32':
            try:
                import winreg
                for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    try:
                        with winreg.OpenKey(hive, r'SOFTWARE\Python\PythonCore') as root:
                            for i in range(winreg.QueryInfoKey(root)[0]):
                                version = winreg.EnumKey(root, i)
                                try:
                                    with winreg.OpenKey(root, version + r'\InstallPath') as key:
                                        candidates.append(str(Path(winreg.QueryValue(key, None)) / 'python.exe'))
                                except OSError:
                                    continue
                    except OSError:
                        continue
            except ImportError:
                pass
    errors = []
    for candidate in dict.fromkeys(candidates):
        try:
            return inspect_python(candidate)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    raise ValueError('No usable external Python 3.13 or newer: ' + '; '.join(errors[-3:]))


def discover_pythons():
    """List usable installed interpreters only when the user opens the editor."""
    candidates = []
    if not getattr(sys, 'frozen', False):
        candidates.append(sys.executable)
    for directory in os.get_exec_path():
        try:
            candidates.extend(str(path) for path in Path(directory).glob('python*.exe')
                              if re.fullmatch(r'python(?:\d+(?:\.\d+)?)?\.exe', path.name,
                                              re.IGNORECASE))
        except OSError:
            continue
    launcher = shutil.which('py')
    if launcher:
        try:
            listing = run_capture([launcher, '-0p'])
            for line in listing.splitlines():
                match = re.search(r'([A-Za-z]:[\\/].*?python(?:\d+(?:\.\d+)?)?\.exe)',
                                  line, re.IGNORECASE)
                if match:
                    candidates.append(match.group(1))
        except (OSError, ValueError):
            pass
    if sys.platform == 'win32':
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, r'SOFTWARE\Python') as root:
                        for company_index in range(winreg.QueryInfoKey(root)[0]):
                            company = winreg.EnumKey(root, company_index)
                            with winreg.OpenKey(root, company) as registrations:
                                for tag_index in range(winreg.QueryInfoKey(registrations)[0]):
                                    tag = winreg.EnumKey(registrations, tag_index)
                                    try:
                                        with winreg.OpenKey(registrations, tag + r'\InstallPath') as key:
                                            try:
                                                path, _ = winreg.QueryValueEx(key, 'ExecutablePath')
                                            except OSError:
                                                path = str(Path(winreg.QueryValue(key, None)) / 'python.exe')
                                            candidates.append(str(path))
                                    except (OSError, TypeError):
                                        continue
                except OSError:
                    continue
        except ImportError:
            pass
    available = []
    seen = set()
    resolved = set()
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file() or str(path).casefold() in seen:
            continue
        seen.add(str(path).casefold())
        try:
            info = inspect_python(path)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        canonical = str(Path(info['path']).resolve()).casefold()
        if canonical not in resolved:
            resolved.add(canonical)
            available.append(info)
    return available


def probe(python, name, quick=False):
    with tempfile.TemporaryDirectory(prefix='pattern-probe-') as tmp:
        target = Path(tmp) / 'probe.json'
        try:
            args = [python, str(worker_entry()), 'probe', name, str(target)]
            if quick:
                args.append('quick')
            run_capture(args, timeout=180)
            result = json.loads(target.read_text(encoding='utf-8'))
            if result.pop('protocol', None) != PROTOCOL:
                raise ValueError('Worker protocol mismatch')
            return result
        except (OSError, ValueError) as exc:
            return {'id': name, 'name': ENGINE_NAMES[name], 'usable': False,
                    'version': None, 'devices': [], 'errors': [str(exc)]}


def choose_engine(engines, requested='auto'):
    available = {e['id']: e for e in engines if e['usable']}
    if requested != 'auto':
        if requested not in available:
            raise ValueError(f'所选计算引擎不可用 / Engine unavailable: {requested}')
        return available[requested]
    for name in PRIORITY:
        if name in available:
            return available[name]
    raise ValueError('没有可用计算引擎 / No usable compute engine')


class ComputeManager:
    def __init__(self, settings, state_path=None):
        self.settings = settings
        self.state_path = Path(state_path) if state_path is not None else None
        self._lock = threading.RLock()
        self._key = None
        self._cache = None
        self._startup_engine = None
        self._device_cursor = 0

    def prepare_startup(self):
        """Synchronously probe the saved engine, or scan all engines on first run/loss."""
        with self._lock:
            saved = None
            if self.state_path is not None:
                try:
                    saved = json.loads(self.state_path.read_text(encoding='utf-8'))
                except (OSError, ValueError, TypeError):
                    pass
            first_run = not isinstance(saved, dict) or saved.get('engine') not in ENGINE_NAMES
            requested = self.settings.get('compute_engine', 'auto')
            target = requested if requested != 'auto' else (saved or {}).get('engine')
            if not first_run and target in ENGINE_NAMES:
                try:
                    python = resolve_python(self.settings.get('compute_python', 'auto'))
                    # 常规启动只验证当前引擎和设备，完整模型探测留给首次启动与手动刷新。
                    checked = probe(python['path'], target, quick=True)
                    if checked['usable']:
                        self._cache = {'python': python, 'engines': [checked], 'error': None}
                        self._key = self.settings.get('compute_python', 'auto')
                        self._startup_engine = target
                        self._save_selected(target)
                        return {'first_run': False, 'rescanned': False,
                                'checked': checked, 'status': self.status()}
                except (ValueError, OSError) as exc:
                    checked = {'id': target, 'name': ENGINE_NAMES[target], 'usable': False,
                               'errors': [str(exc)]}
            else:
                checked = None
            self.inventory(refresh=True)
            status = self.status()
            # Do not replace an explicit unavailable preference with the auto result.
            if not first_run and status.get('selected'):
                self._startup_engine = status['selected']['engine']
                self._save_selected(status['selected']['engine'])
            return {'first_run': first_run, 'rescanned': not first_run,
                    'checked': checked, 'status': status}

    def _save_selected(self, engine):
        if self.state_path is not None:
            from common.persistence import atomic_write_json
            atomic_write_json(self.state_path, {'engine': engine})

    def save_startup_selection(self):
        """Remember auto mode's resolved engine after the first-run choice."""
        selected = self.status().get('selected')
        if selected:
            self._startup_engine = selected['engine']
            self._save_selected(selected['engine'])

    def inventory(self, refresh=False):
        with self._lock:
            configured = self.settings.get('compute_python', 'auto')
            if not refresh and self._cache is not None and self._key == configured:
                return copy.deepcopy(self._cache)
            data = {'python': None, 'engines': [], 'error': None}
            try:
                data['python'] = resolve_python(configured)
                data['engines'] = [probe(data['python']['path'], name) for name in ENGINE_NAMES]
            except (ValueError, OSError) as exc:
                data['error'] = str(exc)
            self._key, self._cache = configured, data
            return copy.deepcopy(data)

    def ensure_engine(self, name):
        """Probe one explicitly requested engine without scanning the registry."""
        if name not in ENGINE_NAMES:
            raise ValueError('Invalid compute engine')
        with self._lock:
            data = self.inventory()
            if data['error'] or any(item['id'] == name for item in data['engines']):
                return
            self._cache['engines'].append(probe(data['python']['path'], name))

    def selection(self, engine='default', device='default', seed=None):
        if not isinstance(engine, str) or engine not in ('default', 'auto', *ENGINE_NAMES):
            raise ValueError('Invalid compute engine')
        if not isinstance(device, str):
            raise ValueError('Invalid compute device')
        requested = self.settings.get('compute_engine', 'auto') if engine == 'default' else engine
        if engine == 'default' and requested == 'auto' and self._startup_engine:
            requested = self._startup_engine
        if requested != 'auto':
            self.ensure_engine(requested)
        data = self.inventory()
        if data['error']:
            raise ValueError(data['error'])
        selected = choose_engine(data['engines'], requested)
        if device == 'default':
            device = self.settings.get('compute_device', 'auto') if engine == 'default' else 'auto'
        devices = selected['devices']
        if device == 'auto':
            chosen = next((d for d in devices if d.get('gpu', d['id'].startswith('cuda:'))), devices[0])
        else:
            chosen = next((d for d in devices if d['id'] == device), None)
            if chosen is None:
                raise ValueError(f'所选设备不可用 / Device unavailable: {device}')
        if seed is None:
            seed = secrets.randbits(32)
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError('seed must be an integer in [0, 2^32)')
        return {'engine': selected['id'], 'engine_name': selected['name'],
                'version': selected['version'], 'python': data['python']['path'],
                'python_version': '.'.join(map(str, data['python']['version'])),
                'device': chosen['id'], 'device_name': chosen['name'],
                'physical_id': chosen.get('physical_id'), 'gpu': chosen.get('gpu', chosen['id'].startswith('cuda:')),
                'cuda': selected.get('cuda'),
                'dtype': 'float32', 'seed': seed, 'protocol': PROTOCOL}

    def submit_global_task(self, queue, payload, client_id, owner, seed=None):
        """Freeze the global choice and enqueue atomically against admin changes."""
        with self._lock:
            selected = self.selection(seed=seed)
            if self.settings.get('compute_device', 'auto') == 'auto' and selected['gpu']:
                engine = next((item for item in self.inventory()['engines']
                               if item['id'] == selected['engine']), None)
                devices = self._parallel_gpu_devices(engine)
                if len(devices) > 1:
                    active = queue.list_waiting() + queue.list_running()
                    usage = {item['id']: sum(task.get('compute', {}).get('device') == item['id']
                                             for task in active) for item in devices}
                    offset = self._device_cursor % len(devices)
                    rotated = devices[offset:] + devices[:offset]
                    chosen = min(rotated, key=lambda item: usage[item['id']])
                    self._device_cursor += 1
                    selected = self.selection(device=chosen['id'], seed=selected['seed'])
            payload['compute'] = selected
            return queue.submit(payload, client_id, owner=owner)

    @staticmethod
    def _parallel_gpu_devices(engine):
        devices = [item for item in (engine or {}).get('devices', []) if item.get('gpu')]
        identities = [item.get('physical_id') for item in devices]
        return devices if identities and all(identities) and len(set(identities)) == len(identities) else devices[:1]

    def hardware_capacity(self, monitor, engine='default', device='default'):
        """Physical CPU packages or independently addressable GPU cards."""
        try:
            selected = self.selection(engine=engine, device=device)
        except ValueError as exc:
            return {'count': 1, 'kind': 'unknown', 'known': False, 'reason': str(exc)}
        if selected['gpu']:
            engine_info = next((item for item in self.inventory()['engines']
                                if item['id'] == selected['engine']), {})
            auto_device = (device == 'auto' or
                           (device == 'default' and self.settings.get('compute_device', 'auto') == 'auto'))
            count = len(self._parallel_gpu_devices(engine_info)) if auto_device else 1
            return {'count': max(1, count), 'kind': 'gpu', 'known': True}
        packages = getattr(monitor, '_cpu_packages', None)
        return {'count': max(1, len(packages)) if packages else 1,
                'kind': 'cpu', 'known': bool(packages)}

    def refresh_if_idle(self, queue):
        """A full refresh may change auto mode, so wait until old tasks finish."""
        with self._lock:
            counts = queue.counts()
            if counts['waiting'] or counts['running']:
                raise ValueError('仍有排队或运行中的任务，请等待完成后再刷新计算引擎')
            return self.status(refresh=True)

    def status(self, refresh=False, public=False):
        data = self.inventory(refresh)
        if refresh:
            self._startup_engine = None
        data['default_engine'] = self.settings.get('compute_engine', 'auto')
        data['default_device'] = self.settings.get('compute_device', 'auto')
        try:
            data['selected'] = self.selection()
        except ValueError as exc:
            data['selected'] = None
            data['selection_error'] = str(exc)
        data['engines'] = self.inventory()['engines']
        if refresh and data['selected']:
            self._startup_engine = data['selected']['engine']
            self._save_selected(data['selected']['engine'])
        if public:
            if data['python']:
                data['python'].pop('path', None)
            if data['selected']:
                data['selected'].pop('python', None)
        return data


def diagnostics(output, python='auto', engine='auto'):
    """Opt-in packaged smoke check; never reads or changes application settings."""
    from core.config import MODEL_CONFIGS
    from core.task_worker import execute_isolated_task
    manager = ComputeManager({'compute_python': python, 'compute_engine': engine})
    report = manager.status(refresh=True)
    if report['selected']:
        payload = {'compute': manager.selection(seed=42), 'type': 'simulate', 'model': '模型1',
                   'params': MODEL_CONFIGS['模型1']['defaults'], 'iterations': 3,
                   'init_x_range': [.8, 1.], 'init_y_range': [.5, .6], 'track_points': []}
        result = execute_isolated_task(payload, None, lambda: False, lambda p: None)
        report['smoke'] = {'completed': True, 'compute': result['compute'],
                           'has_plot': bool(result['viz_2d'])}
    else:
        report['smoke'] = {'completed': False}
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
