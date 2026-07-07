"""
Worker 进程
==========
子进程入口：接收任务 → 执行模拟 → 返回结果。
每个 worker 独立加载 PyTorch 模拟器，独占 GPU 上下文。
"""
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import torch
from app.simulator import PatternSimulator


def worker_loop(pipe, worker_id, use_cuda):
    """子进程主循环

    pipe: multiprocessing.Connection — 与主进程的双向通信管道
    worker_id: int — 工作器编号
    use_cuda: bool — 是否尝试使用 GPU
    """
    if use_cuda and torch.cuda.is_available():
        if torch.cuda.device_count() > 1:
            torch.cuda.set_device(worker_id % torch.cuda.device_count())

    simulator = PatternSimulator(grid_size=100, use_cuda=use_cuda)
    print(f"[Worker {worker_id}] 初始化完成，设备: {simulator.hardware_info}")

    while True:
        msg = pipe.recv()
        if msg is None:
            break

        try:
            job = msg
            job_id = job["job_id"]

            pipe.send({"type": "progress", "job_id": job_id, "progress": 0})

            if job["job_type"] == "simulate":
                n_iter = min(job["iterations"], 20000)

                x_data, y_data, evolution = simulator.simulate(
                    job["model"],
                    job["params"],
                    n_iter,
                    tuple(job["init_x_range"]),
                    tuple(job["init_y_range"]),
                    job.get("track_points", []),
                )

                result = {
                    "x_data": x_data.tolist(),
                    "y_data": y_data.tolist(),
                    "evolution": _evolution_to_dict(evolution),
                    "hardware_info": simulator.hardware_info,
                }
            elif job["job_type"] == "animate":
                n_frames = min(job.get("frames", 300), 1000)

                x_hist, y_hist = simulator.simulate_with_history(
                    job["model"],
                    job["params"],
                    n_frames,
                    tuple(job["init_x_range"]),
                    tuple(job["init_y_range"]),
                )

                result = {
                    "x_history": x_hist.tolist(),
                    "y_history": y_hist.tolist(),
                    "hardware_info": simulator.hardware_info,
                }

            pipe.send({"type": "result", "job_id": job_id, "result": result})

        except Exception as e:
            import traceback
            pipe.send({
                "type": "error",
                "job_id": job.get("job_id", "unknown"),
                "error": str(e),
                "traceback": traceback.format_exc(),
            })

    print(f"[Worker {worker_id}] 已退出")


def _evolution_to_dict(evolution):
    """将 evolution 内嵌的 list 转成纯 Python 类型"""
    result = {}
    for key, val in evolution.items():
        result[key] = {
            "x": [float(v) for v in val["x"]],
            "y": [float(v) for v in val["y"]],
        }
    return result
