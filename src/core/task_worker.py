"""External Python task bridge. Main service never imports engine runtimes."""
import json
from pathlib import Path
import tempfile
import time

from common.compute import PROTOCOL, popen, worker_entry
from core.simulation import SimulationCancelled
from core.visualization import PatternVisualizer


def execute_isolated_task(payload, device_id, is_cancelled, set_progress):
    import numpy as np
    compute = payload['compute']
    with tempfile.TemporaryDirectory(prefix='pattern-task-') as tmp:
        directory = Path(tmp)
        (directory / 'request.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        with (directory / 'worker.log').open('w', encoding='utf-8') as log:
            worker = popen([compute['python'], str(worker_entry()), 'run', tmp],
                           stdout=log, stderr=log, stdin=-3)
            cancelled_at = None
            try:
                while worker.poll() is None:
                    if is_cancelled():
                        if cancelled_at is None:
                            (directory / 'cancel').touch()
                            cancelled_at = time.monotonic()
                        if time.monotonic() - cancelled_at > 10:
                            worker.kill()
                            raise SimulationCancelled('取消任务超时，已结束计算进程')
                    try:
                        set_progress(json.loads((directory / 'progress.json').read_text(encoding='utf-8'))['progress'])
                    except (OSError, ValueError, KeyError):
                        pass
                    time.sleep(.05)
            finally:
                if worker.poll() is None:
                    worker.kill()
                worker.wait(timeout=10)
        if is_cancelled():
            raise SimulationCancelled('任务已被取消')
        try:
            outcome = json.loads((directory / 'outcome.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            detail = (directory / 'worker.log').read_text(encoding='utf-8', errors='replace')[-2000:]
            raise RuntimeError(f'计算进程异常退出 ({worker.returncode}): {detail}') from exc
        if outcome.get('protocol') != PROTOCOL:
            raise RuntimeError('Worker protocol mismatch')
        if outcome['status'] == 'cancelled':
            raise SimulationCancelled(outcome.get('error'))
        if outcome['status'] != 'completed' or worker.returncode:
            raise RuntimeError(outcome.get('error', '计算进程失败'))
        with np.load(directory / 'arrays.npz', allow_pickle=False) as arrays:
            x, y = arrays['x'], arrays['y']
        visualizer = PatternVisualizer()
        model = payload['model']
        metadata = {k: v for k, v in compute.items() if k != 'python'}
        if payload['type'] == 'simulate':
            evolution = json.loads((directory / 'evolution.json').read_text(encoding='utf-8'))
            result = {
                'viz_2d': visualizer.create_comprehensive_plot(x, y, evolution, payload.get('track_points'),
                                                             model, lang=payload.get('lang', 'zh-CN')),
                'viz_3d': visualizer.create_3d_pattern(x, model, lang=payload.get('lang', 'zh-CN')),
                'model': model, 'iterations': payload['iterations'], 'compute': metadata,
            }
        else:
            result = {'animation': visualizer.create_animation_frames(x, y, start_iteration=payload['start_frame']),
                      'model': model, 'start_iteration': payload['start_frame'], 'compute': metadata}
        if is_cancelled():
            raise SimulationCancelled('任务已被取消')
        set_progress(100)
        return result
