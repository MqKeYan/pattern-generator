"""Engine-independent simulation; optional runtimes are loaded inside workers."""
from core.config import MODEL_INIT_RANGES, GRID_SIZE


class SimulationCancelled(Exception):
    pass


def estimate_vram_mb(grid_size=GRID_SIZE):
    return int(500 + grid_size * grid_size * 4 * 12 * 2 / 1048576 + 1)


def estimate_host_ram_mb(frames, grid_size=GRID_SIZE):
    return int(frames * grid_size * grid_size * 8 / 1048576 + 1)


class PatternSimulator:
    def __init__(self, grid_size=GRID_SIZE, use_cuda=False, *, engine='pytorch',
                 device=None, seed=None):
        import numpy as np
        from core.engines import create_engine
        self.grid_size = grid_size
        self.backend = create_engine(engine, device or ('cuda:0' if use_cuda else 'cpu'))
        self.device = self.backend.device
        self.use_cuda = self.backend.gpu
        self.rng = np.random.default_rng(seed)

    @staticmethod
    def _check_cancel(cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            raise SimulationCancelled('任务已被取消')

    def initialize_grid(self, model_name='模型1', x_range=None, y_range=None, device=None):
        import numpy as np
        ranges = MODEL_INIT_RANGES[model_name]
        values = []
        for low, high in (x_range or ranges['x_range'], y_range or ranges['y_range']):
            arr = self.rng.random((self.grid_size, self.grid_size), dtype=np.float32)
            arr = arr * np.float32(high - low) + np.float32(low)
            values.append(self.backend.array(np.maximum(arr, np.float32(1e-6))))
        return tuple(values)

    def _initial(self, model, x_range, y_range):
        default = (0.1, 1.0)
        if tuple(x_range) == default and tuple(y_range) == default:
            return self.initialize_grid(model)
        return self.initialize_grid(model, x_range, y_range)

    def _run(self, model_name, params, iterations, init_x_range, init_y_range,
             track_points, cancel_event, progress_cb, start_from=None):
        import numpy as np
        from core.models import MODEL_FUNCS
        b = self.backend
        evolution = {'center': {'x': [], 'y': []}}
        points = {'center': (self.grid_size // 2, self.grid_size // 2)}
        for point in track_points or []:
            key = f"point_{point['x']}_{point['y']}"
            points[key] = (point['x'], point['y'])
            evolution[key] = {'x': [], 'y': []}
        history_x, history_y = [], []
        try:
            with b.context():
                x, y = self._initial(model_name, init_x_range, init_y_range)
                p = b.array(params)
                previous_progress = -1
                for i in range(iterations):
                    self._check_cancel(cancel_event)
                    if start_from is not None and i >= start_from:
                        history_x.append(b.host(x))
                        history_y.append(b.host(y))
                    if getattr(b, 'custom_step', False):
                        x_new, y_new = b.step(list(MODEL_FUNCS).index(model_name), x, y, p)
                    else:
                        x_new, y_new = MODEL_FUNCS[model_name](x, y, p, b)
                    if start_from is None:
                        for key, (px, py) in points.items():
                            valid = 0 <= px < self.grid_size and 0 <= py < self.grid_size
                            evolution[key]['x'].append((b.scalar(x, px, py) if getattr(b, 'custom_step', False)
                                                        else float(x[px, py].item())) if valid else 0.)
                            evolution[key]['y'].append((b.scalar(y, px, py) if getattr(b, 'custom_step', False)
                                                        else float(y[px, py].item())) if valid else 0.)
                    x, y = ((x_new, y_new) if getattr(b, 'custom_step', False)
                            else (b.clamp(x_new), b.clamp(y_new)))
                    progress = round((i + 1) / iterations * 100)
                    if progress_cb and progress != previous_progress:
                        progress_cb(progress)
                        previous_progress = progress
                    if i % 128 == 0 or i == iterations - 1:
                        b.synchronize()
                        if not np.isfinite(b.host(x)).all() or not np.isfinite(b.host(y)).all():
                            raise ValueError('模型计算产生 NaN/Inf，请检查参数')
                self._check_cancel(cancel_event)
                if start_from is not None:
                    return np.asarray(history_x, dtype=np.float32), np.asarray(history_y, dtype=np.float32)
                return b.host(x), b.host(y), evolution
        finally:
            b.release()

    def simulate(self, model_name, params, iterations=1000, init_x_range=(.1, 1.),
                 init_y_range=(.1, 1.), track_points=None, cancel_event=None,
                 progress_cb=None, device_id=None):
        return self._run(model_name, params, iterations, init_x_range, init_y_range,
                         track_points, cancel_event, progress_cb)

    def simulate_with_history(self, model_name, params, iterations=100, start_from=0,
                              init_x_range=(.1, 1.), init_y_range=(.1, 1.),
                              cancel_event=None, progress_cb=None, device_id=None):
        return self._run(model_name, params, iterations, init_x_range, init_y_range,
                         None, cancel_event, progress_cb, start_from)
