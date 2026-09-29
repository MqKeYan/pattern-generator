"""Worker-only adapters. Optional runtimes are imported only when selected."""
import importlib
import contextlib
import os

ENGINE_NAMES = {'pytorch': 'PyTorch', 'cupy': 'CuPy', 'warp': 'NVIDIA Warp',
                'taichi': 'Taichi', 'pyopencl': 'PyOpenCL',
                'numba': 'Numba', 'numpy': 'NumPy'}
ARRAY_ENGINE_NAMES = ('pytorch', 'cupy', 'numpy')

class ArrayEngine:
    def __init__(self, name, device='cpu'):
        if name not in ARRAY_ENGINE_NAMES:
            raise ValueError(f'Unknown engine: {name}')
        self.name, self.device = name, device
        self.xp = importlib.import_module('torch' if name == 'pytorch' else name)
        self.version = self.xp.__version__
        self.gpu = device.startswith('cuda:')
        if device != 'cpu' and not self.gpu:
            raise ValueError(f'Invalid device: {device}')
        if name == 'numpy' and device != 'cpu':
            raise ValueError('NumPy requires CPU')
        if name == 'cupy' and not self.gpu:
            raise ValueError('CuPy requires CUDA')
        self.index = int(device.split(':')[1]) if self.gpu else None
        if self.index is not None and self.index < 0:
            raise ValueError('Invalid CUDA index')

    def context(self):
        if not self.gpu:
            return contextlib.nullcontext()
        return (self.xp.cuda.device(self.index) if self.name == 'pytorch'
                else self.xp.cuda.Device(self.index))

    def array(self, data):
        if self.name == 'pytorch':
            return self.xp.as_tensor(data, dtype=self.xp.float32, device=self.device)
        return self.xp.asarray(data, dtype=self.xp.float32)

    def roll(self, value, shift, axis):
        return self.xp.roll(value, shift, axis)

    def exp(self, value):
        return self.xp.exp(value)

    def clamp(self, value, min=1e-6):
        if self.name == 'pytorch':
            return self.xp.clamp(value, min=min)
        return self.xp.maximum(value, self.xp.float32(min))

    def host(self, value):
        if self.name == 'pytorch':
            return value.detach().cpu().numpy().copy()
        if self.name == 'cupy':
            return self.xp.asnumpy(value).copy()
        return value.copy()

    def synchronize(self):
        if self.gpu:
            if self.name == 'pytorch':
                self.xp.cuda.synchronize(self.index)
            else:
                self.xp.cuda.get_current_stream().synchronize()

    def physical_id(self):
        """Stable identity of the selected GPU, independent of CUDA ordinal."""
        if not self.gpu:
            return 'cpu'
        if self.name == 'pytorch':
            props = self.xp.cuda.get_device_properties(self.index)
            return str(getattr(props, 'uuid', '') or '') or None
        return 'pci:' + self.xp.cuda.Device(self.index).pci_bus_id.lower()

    def release(self):
        if self.gpu:
            with self.context():
                self.synchronize()
                if self.name == 'pytorch':
                    self.xp.cuda.empty_cache()
                else:
                    self.xp.get_default_memory_pool().free_all_blocks()
                    self.xp.get_default_pinned_memory_pool().free_all_blocks()


class NumbaEngine:
    custom_step = True
    def __init__(self, device='cpu'):
        if device != 'cpu':
            raise ValueError('Numba batch-2 backend requires CPU')
        import numba
        import numpy as np
        from core import numba_kernels
        self.name, self.device, self.gpu = 'numba', 'cpu', False
        self.version = numba.__version__
        self.np, self.numba, self.kernels = np, numba, numba_kernels
        # Each task owns one process; cap threads so concurrent jobs do not oversubscribe CPUs.
        numba.set_num_threads(min(numba.get_num_threads(), max(1, min(4, (os.cpu_count() or 2) // 2))))
        self._buffers = None
        self._turn = 0

    def context(self):
        return contextlib.nullcontext()

    def array(self, data):
        return self.np.asarray(data, dtype=self.np.float32)

    def step(self, model, x, y, p):
        if self._buffers is None or self._buffers[0][0].shape != x.shape:
            self._buffers = tuple((self.np.empty_like(x), self.np.empty_like(y)) for _ in range(2))
        out = self._buffers[self._turn]
        self._turn = 1 - self._turn
        kernel = self.kernels.step_parallel if x.shape[0] >= 64 else self.kernels.step_serial
        kernel(model, x, y, p, *out)
        return out

    def host(self, value):
        return value.copy()

    def scalar(self, value, row, col):
        return float(value[row, col])

    def synchronize(self):
        pass

    def physical_id(self):
        return 'cpu'

    def release(self):
        self._buffers = None


class WarpEngine:
    custom_step = True
    def __init__(self, device='cpu'):
        import warp as wp
        from core import warp_kernels
        wp.init()
        target = wp.get_device(device)
        if device != 'cpu' and (not device.startswith('cuda:') or not target.is_cuda):
            raise ValueError(f'Invalid Warp device: {device}')
        self.name, self.device, self.gpu = 'warp', device, target.is_cuda
        self.version, self.wp, self.kernels = wp.__version__, wp, warp_kernels
        self.target = target
        self._buffers = None
        self._turn = 0

    def context(self):
        return contextlib.nullcontext()

    def array(self, data):
        import numpy as np
        return self.wp.array(np.asarray(data, dtype=np.float32), dtype=self.wp.float32, device=self.device)

    def step(self, model, x, y, p):
        if self._buffers is None or self._buffers[0][0].shape != x.shape:
            self._buffers = tuple((self.wp.empty(x.shape, dtype=self.wp.float32, device=self.device),
                                   self.wp.empty(y.shape, dtype=self.wp.float32, device=self.device)) for _ in range(2))
        out = self._buffers[self._turn]
        self._turn = 1 - self._turn
        self.wp.launch(self.kernels.step, dim=x.shape,
                       inputs=[model, x, y, p, *out, *x.shape], device=self.device)
        return out

    def host(self, value):
        return value.numpy().copy()

    def scalar(self, value, row, col):
        return float(value.numpy()[row, col])

    def synchronize(self):
        if self.gpu:
            self.wp.synchronize_device(self.target)

    def physical_id(self):
        if not self.gpu:
            return 'cpu'
        if self.target.uuid:
            return str(self.target.uuid)
        if self.target.pci_bus_id:
            return 'pci:' + self.target.pci_bus_id.lower() + '.0'
        return None

    def release(self):
        self.synchronize()
        self._buffers = None


class TaichiEngine:
    custom_step = True
    def __init__(self, device='cpu'):
        if device not in ('cpu', 'cuda:0', 'vulkan:0'):
            raise ValueError(f'Unsupported Taichi device: {device}')
        if device == 'cuda:0':
            os.environ['CUDA_VISIBLE_DEVICES'] = '0'
        elif device == 'vulkan:0':
            os.environ['TI_VISIBLE_DEVICE'] = '0'
        import taichi as ti
        import numpy as np
        from core import taichi_kernels
        self.name, self.device, self.gpu = 'taichi', device, device != 'cpu'
        self.version = '.'.join(map(str, ti.__version__)) if isinstance(ti.__version__, tuple) else str(ti.__version__)
        self.ti, self.np, self.kernels = ti, np, taichi_kernels
        self._buffers = None
        self._turn = 0
        ti.reset()
        cache = os.environ.get('TAICHI_CACHE_DIR')
        options = {'arch': {'cpu': ti.cpu, 'cuda:0': ti.cuda, 'vulkan:0': ti.vulkan}[device],
                   'enable_fallback': False, 'fast_math': False, 'offline_cache': True,
                   'cpu_max_num_threads': min(4, os.cpu_count() or 1)}
        if cache:
            from pathlib import Path
            Path(cache).mkdir(parents=True, exist_ok=True)
            options['offline_cache_file_path'] = cache
        ti.init(**options)

    def context(self):
        return contextlib.nullcontext()

    def array(self, data):
        data = self.np.asarray(data, dtype=self.np.float32)
        result = self.ti.ndarray(dtype=self.ti.f32, shape=data.shape)
        result.from_numpy(data)
        return result

    def step(self, model, x, y, p):
        if self._buffers is None or self._buffers[0][0].shape != x.shape:
            self._buffers = tuple((self.ti.ndarray(dtype=self.ti.f32, shape=x.shape),
                                   self.ti.ndarray(dtype=self.ti.f32, shape=y.shape)) for _ in range(2))
        out = self._buffers[self._turn]
        self._turn = 1 - self._turn
        self.kernels.step(model, x, y, p, *out, *x.shape)
        return out

    def host(self, value):
        return value.to_numpy().copy()

    def scalar(self, value, row, col):
        return float(value[row, col])

    def synchronize(self):
        self.ti.sync()

    def physical_id(self):
        if not self.gpu:
            return 'cpu'
        if self.device == 'cuda:0':
            try:
                import pynvml
                pynvml.nvmlInit()
                try:
                    identity = pynvml.nvmlDeviceGetUUID(pynvml.nvmlDeviceGetHandleByIndex(0))
                    return identity.decode() if isinstance(identity, bytes) else str(identity)
                finally:
                    pynvml.nvmlShutdown()
            except Exception:
                return None
        return None  # Vulkan device identity is not exposed by this Taichi API.

    def release(self):
        self.synchronize()
        self._buffers = None
        self.ti.reset()


class OpenCLArray:
    def __init__(self, buffer, shape):
        self.buffer, self.shape = buffer, shape


class PyOpenCLEngine:
    custom_step = True
    def __init__(self, device):
        import pyopencl as cl
        import numpy as np
        from pathlib import Path
        parts = device.split(':')
        if len(parts) != 3 or parts[0] != 'opencl' or not all(s.isdigit() for s in parts[1:]):
            raise ValueError(f'Invalid OpenCL device: {device}')
        platform_index, device_index = map(int, parts[1:])
        platform = cl.get_platforms()[platform_index]
        target = platform.get_devices()[device_index]
        self.name, self.device = 'pyopencl', device
        self.gpu = not bool(target.type & cl.device_type.CPU)
        self.version, self.cl, self.np = cl.__version__, cl, np
        self.platform, self.target = platform, target
        self.cl_context = cl.Context([target])
        self.queue = cl.CommandQueue(self.cl_context, device=target)
        source = (Path(__file__).parent / 'opencl_kernels.cl').read_text(encoding='utf-8')
        try:
            self.program = cl.Program(self.cl_context, source).build(options=['-cl-std=CL1.2'])
        except Exception as exc:
            raise RuntimeError(f'OpenCL kernel build failed on {target.name}: {exc}') from exc
        self._buffers = None
        self._turn = 0

    def context(self):
        return contextlib.nullcontext()

    def array(self, data):
        data = self.np.ascontiguousarray(data, dtype=self.np.float32)
        buffer = self.cl.Buffer(self.cl_context, self.cl.mem_flags.READ_WRITE | self.cl.mem_flags.COPY_HOST_PTR,
                                hostbuf=data)
        return OpenCLArray(buffer, data.shape)

    def step(self, model, x, y, p):
        if self._buffers is None or self._buffers[0][0].shape != x.shape:
            size = x.shape[0] * x.shape[1] * 4
            self._buffers = tuple((OpenCLArray(self.cl.Buffer(self.cl_context, self.cl.mem_flags.READ_WRITE, size), x.shape),
                                   OpenCLArray(self.cl.Buffer(self.cl_context, self.cl.mem_flags.READ_WRITE, size), y.shape))
                                  for _ in range(2))
        out = self._buffers[self._turn]
        self._turn = 1 - self._turn
        self.program.step(self.queue, x.shape, None, self.np.int32(model), x.buffer, y.buffer, p.buffer,
                          out[0].buffer, out[1].buffer, self.np.int32(x.shape[0]), self.np.int32(x.shape[1]))
        return out

    def host(self, value):
        data = self.np.empty(value.shape, dtype=self.np.float32)
        self.cl.enqueue_copy(self.queue, data, value.buffer).wait()
        return data

    def scalar(self, value, row, col):
        return float(self.host(value)[row, col])

    def synchronize(self):
        self.queue.finish()

    def physical_id(self):
        if not self.gpu:
            return 'cpu'
        info = getattr(self.cl.device_info, 'UUID_KHR', None)
        if info is not None:
            try:
                import uuid
                return 'GPU-' + str(uuid.UUID(bytes=bytes(self.target.get_info(info))))
            except Exception:
                pass
        info = getattr(self.cl.device_info, 'PCI_BUS_INFO_KHR', None)
        if info is not None:
            try:
                pci = self.target.get_info(info)
                return f'pci:{pci.pci_domain:04x}:{pci.pci_bus:02x}:{pci.pci_device:02x}.{pci.pci_function:x}'
            except Exception:
                pass
        import hashlib
        identity = '|'.join(str(value) for value in (
            self.platform.vendor, self.platform.name, self.platform.version,
            self.target.vendor, self.target.name, self.target.version, self.target.driver_version))
        return 'opencl-fingerprint:' + hashlib.sha256(identity.encode('utf-8')).hexdigest()

    def release(self):
        self.synchronize()
        self._buffers = None


def create_engine(name, device='cpu'):
    if name == 'numba':
        return NumbaEngine(device)
    if name == 'warp':
        return WarpEngine(device)
    if name == 'taichi':
        return TaichiEngine(device)
    if name == 'pyopencl':
        return PyOpenCLEngine(device)
    return ArrayEngine(name, device)


def probe_engine(name, quick=False):
    """检查引擎设备；完整探测时执行每个设备上的五个模型。"""
    import numpy as np
    from core.config import MODEL_CONFIGS
    from core.models import MODEL_FUNCS
    info = {'id': name, 'name': ENGINE_NAMES[name], 'usable': False,
            'version': None, 'devices': [], 'errors': []}
    try:
        xp = importlib.import_module('torch' if name == 'pytorch' else name)
        info['version'] = ('.'.join(map(str, xp.__version__))
                           if isinstance(xp.__version__, tuple) else str(xp.__version__))
        candidates = ['cpu'] if name not in ('cupy', 'pyopencl', 'taichi') else []
        cpu_only = os.environ.get('PATTERN_COMPUTE_CPU_ONLY') == '1'
        if name == 'warp':
            xp.init()
            if not cpu_only:
                candidates += [str(device.alias) for device in xp.get_cuda_devices()]
        elif name == 'taichi':
            if not cpu_only:
                try:
                    import pynvml
                    pynvml.nvmlInit()
                    try:
                        if pynvml.nvmlDeviceGetCount() > 0:
                            candidates.append('cuda:0')
                    finally:
                        pynvml.nvmlShutdown()
                except Exception:
                    pass
                candidates.append('vulkan:0')
            candidates.append('cpu')
        elif name == 'pyopencl':
            for platform_index, platform in enumerate(xp.get_platforms()):
                for device_index, target in enumerate(platform.get_devices()):
                    if cpu_only and not target.type & xp.device_type.CPU:
                        continue
                    candidates.append(f'opencl:{platform_index}:{device_index}')
            if not candidates and cpu_only:
                info['errors'].append('No CPU OpenCL device; GPU validation deferred')
        elif name in ('pytorch', 'cupy'):
            try:
                count = (xp.cuda.device_count() if name == 'pytorch'
                         else xp.cuda.runtime.getDeviceCount())
                if not cpu_only:
                    candidates += [f'cuda:{i}' for i in range(count)]
            except Exception as exc:
                info['errors'].append(f'CUDA: {type(exc).__name__}: {exc}')
        for device in candidates:
            try:
                engine = create_engine(name, device)
                with engine.context():
                    if quick:
                        # 往返一次小数组，确认当前设备可分配和读取。
                        x = engine.array(np.full((4, 4), .8, dtype=np.float32))
                        engine.synchronize()
                        if not np.isfinite(engine.host(x)).all():
                            raise RuntimeError('引擎就绪检测结果包含 NaN/Inf')
                    else:
                        for model, cfg in MODEL_CONFIGS.items():
                            x = engine.array(np.full((4, 4), .8, dtype=np.float32))
                            y = engine.array(np.full((4, 4), .5, dtype=np.float32))
                            params = engine.array(cfg['defaults'])
                            out = (engine.step(list(MODEL_CONFIGS).index(model), x, y, params)
                                   if getattr(engine, 'custom_step', False)
                                   else MODEL_FUNCS[model](x, y, params, engine))
                            engine.synchronize()
                            if not all(np.isfinite(engine.host(v)).all() for v in out):
                                raise RuntimeError('Model probe produced NaN/Inf')
                    item = {'id': device, 'name': 'CPU', 'physical_id': 'cpu',
                            'free_mb': None, 'gpu': engine.gpu}
                    if engine.gpu:
                        if name == 'pytorch':
                            props = xp.cuda.get_device_properties(engine.index)
                            item['name'] = props.name
                            item['physical_id'] = engine.physical_id()
                            item['free_mb'] = xp.cuda.mem_get_info(engine.index)[0] / 1048576
                            info['cuda'] = xp.version.cuda
                        elif name == 'cupy':
                            props = xp.cuda.runtime.getDeviceProperties(engine.index)
                            label = props['name']
                            item['name'] = label.decode() if isinstance(label, bytes) else str(label)
                            item['physical_id'] = engine.physical_id()
                            item['free_mb'] = xp.cuda.runtime.memGetInfo()[0] / 1048576
                            info['cuda'] = str(xp.cuda.runtime.runtimeGetVersion())
                        elif name == 'warp':
                            item['name'] = engine.target.name
                            item['physical_id'] = engine.physical_id()
                            item['free_mb'] = engine.target.free_memory / 1048576
                            info['cuda'] = str(getattr(xp.config, 'cuda_toolkit_version', 'unknown'))
                        elif name == 'taichi':
                            item['name'] = 'Taichi ' + device.upper()
                            item['physical_id'] = engine.physical_id()
                        else:
                            item['name'] = engine.platform.name + ' / ' + engine.target.name
                            item['physical_id'] = engine.physical_id()
                    elif name == 'pyopencl':
                        item['name'] = engine.platform.name + ' / ' + engine.target.name
                    info['devices'].append(item)
                    if quick:
                        del x
                    else:
                        del x, y, out
                    engine.release()
            except Exception as exc:
                info['errors'].append(f'{device}: {type(exc).__name__}: {exc}')
        if name == 'pyopencl':
            identities = [item['physical_id'] for item in info['devices'] if item['gpu']]
            duplicates = {identity for identity in identities if identity and identities.count(identity) > 1}
            if duplicates:
                info['devices'] = [item for item in info['devices'] if item['physical_id'] not in duplicates]
                info['errors'].append('Indistinguishable OpenCL devices; cannot select a stable physical device')
        info['usable'] = bool(info['devices'])
        if not info['usable'] and not info['errors']:
            info['errors'].append('No usable devices')
    except Exception as exc:
        info['errors'].append(f'{type(exc).__name__}: {exc}')
    return info
