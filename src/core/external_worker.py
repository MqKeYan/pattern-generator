"""Standalone entry shipped as application source, executed by external Python."""
import json
import os
from pathlib import Path
import sys
import traceback
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PROTOCOL = 1


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            # Windows readers briefly hold a handle without delete sharing.
            if attempt == 19:
                raise
            time.sleep(.01)


def main():
    if sys.argv[1] == 'probe':
        from core.engines import probe_engine
        quick = len(sys.argv) > 4 and sys.argv[4] == 'quick'
        write_json(sys.argv[3], dict(probe_engine(sys.argv[2], quick=quick), protocol=PROTOCOL))
        return
    directory = Path(sys.argv[2])
    try:
        import numpy as np
        from core.simulation import PatternSimulator, SimulationCancelled
        payload = json.loads((directory / 'request.json').read_text(encoding='utf-8'))
        compute = payload['compute']
        if compute['protocol'] != PROTOCOL:
            raise ValueError('Worker protocol mismatch')
        if compute['python_version'] != '.'.join(map(str, sys.version_info[:3])):
            raise ValueError('Python version changed since submission; resubmit the task')
        simulator = PatternSimulator(engine=compute['engine'], device=compute['device'], seed=compute['seed'])
        if simulator.backend.version != compute['version']:
            raise ValueError('Engine version changed since submission; resubmit the task')
        if compute.get('physical_id') and simulator.backend.physical_id() != compute['physical_id']:
            raise ValueError('Compute device changed since submission; refresh engines and resubmit the task')
        class Cancellation:
            def is_set(self):
                return (directory / 'cancel').exists()
        def progress(value):
            write_json(directory / 'progress.json', {'progress': value})
        kwargs = dict(init_x_range=payload['init_x_range'], init_y_range=payload['init_y_range'],
                      cancel_event=Cancellation(), progress_cb=progress)
        if payload['type'] == 'simulate':
            x, y, evolution = simulator.simulate(payload['model'], payload['params'],
                payload['iterations'], track_points=payload.get('track_points'), **kwargs)
            np.savez(directory / 'arrays.npz', x=x, y=y)
            write_json(directory / 'evolution.json', evolution)
        elif payload['type'] == 'animate':
            x, y = simulator.simulate_with_history(payload['model'], payload['params'],
                payload['start_frame'] + payload['frames'], start_from=payload['start_frame'], **kwargs)
            np.savez(directory / 'arrays.npz', x=x, y=y)
        else:
            raise ValueError('Unknown task type')
        write_json(directory / 'outcome.json', {'protocol': PROTOCOL, 'status': 'completed'})
    except Exception as exc:
        status = 'cancelled' if type(exc).__name__ == 'SimulationCancelled' else 'error'
        write_json(directory / 'outcome.json',
                   {'protocol': PROTOCOL, 'status': status, 'error': str(exc)})
        traceback.print_exc()


if __name__ == '__main__':
    main()
