"""独立计算子进程：任务结束后由操作系统回收其计算运行时内存。"""

import gc
import multiprocessing as mp
import queue
import time
import traceback

from core.config import GRID_SIZE
from core.simulation import PatternSimulator, SimulationCancelled
from core.visualization import PatternVisualizer


def _send_progress(progress_queue, value):
    try:
        progress_queue.put_nowait(value)
    except queue.Full:
        pass


def _release_worker_memory(use_cuda):
    gc.collect()
    if use_cuda:
        try:
            import torch
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        except Exception:
            pass


def _run_worker(payload, device_id, cancel_event, progress_queue, result_queue):
    """子进程入口，只传递可序列化结果，避免计算运行时留在主服务。"""
    use_cuda = False
    try:
        import torch
        use_cuda = torch.cuda.is_available()
        simulator = PatternSimulator(grid_size=GRID_SIZE, use_cuda=use_cuda)
        visualizer = PatternVisualizer()

        def progress_callback(value):
            _send_progress(progress_queue, value)

        model = payload['model']
        params = payload['params']
        if payload['type'] == 'simulate':
            x_data, y_data, evolution_data = simulator.simulate(
                model, params, payload['iterations'],
                init_x_range=payload['init_x_range'],
                init_y_range=payload['init_y_range'],
                track_points=payload.get('track_points'),
                cancel_event=cancel_event,
                progress_cb=progress_callback,
                device_id=device_id,
            )
            result = {
                'viz_2d': visualizer.create_comprehensive_plot(
                    x_data, y_data, evolution_data, payload.get('track_points'), model,
                    lang=payload.get('lang', 'zh-CN'),
                ),
                'viz_3d': visualizer.create_3d_pattern(
                    x_data, model, lang=payload.get('lang', 'zh-CN'),
                ),
                'model': model,
                'iterations': payload['iterations'],
            }
        elif payload['type'] == 'animate':
            total_iterations = payload['frames'] + payload['start_frame']
            x_history, y_history = simulator.simulate_with_history(
                model, params, total_iterations,
                start_from=payload['start_frame'],
                init_x_range=payload['init_x_range'],
                init_y_range=payload['init_y_range'],
                cancel_event=cancel_event,
                progress_cb=progress_callback,
                device_id=device_id,
            )
            result = {
                'animation': visualizer.create_animation_frames(
                    x_history, y_history, start_iteration=payload['start_frame'],
                ),
                'model': model,
                'start_iteration': payload['start_frame'],
            }
        else:
            raise ValueError(f"未知任务类型: {payload['type']}")
        result_queue.put(('completed', result))
    except SimulationCancelled as exc:
        result_queue.put(('cancelled', str(exc)))
    except Exception:
        result_queue.put(('error', traceback.format_exc()))
    finally:
        _release_worker_memory(use_cuda)


def execute_isolated_task(payload, device_id, is_cancelled, set_progress):
    """在独立进程中执行任务，并将进度、取消和结果桥接给主服务。"""
    context = mp.get_context('spawn')
    cancel_event = context.Event()
    progress_queue = context.Queue(maxsize=32)
    result_queue = context.Queue(maxsize=1)
    worker = context.Process(
        target=_run_worker,
        args=(payload, device_id, cancel_event, progress_queue, result_queue),
        name='pattern-task-worker',
    )
    worker.start()
    outcome = None
    cancel_requested_at = None

    def drain_progress():
        while True:
            try:
                set_progress(progress_queue.get_nowait())
            except queue.Empty:
                return

    try:
        while outcome is None:
            drain_progress()

            if is_cancelled() and not cancel_event.is_set():
                cancel_event.set()
                cancel_requested_at = time.monotonic()

            try:
                outcome = result_queue.get(timeout=0.1)
                continue
            except queue.Empty:
                pass

            if cancel_requested_at and time.monotonic() - cancel_requested_at > 10:
                worker.terminate()
                raise SimulationCancelled('取消任务超时')
            if not worker.is_alive():
                raise RuntimeError('计算子进程异常退出，未返回结果')
        drain_progress()
    finally:
        worker.join(timeout=10)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2)
        progress_queue.close()
        result_queue.close()

    status, data = outcome
    if status == 'completed':
        return data
    if status == 'cancelled':
        raise SimulationCancelled(data or '任务已取消')
    raise RuntimeError(data or '计算子进程执行失败')
