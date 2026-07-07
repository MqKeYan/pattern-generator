"""
Worker 进程池管理
===============
管理子进程的创建、销毁、任务分发和状态查询。
主进程维护一个 deque 作为待办队列，空闲 worker 领取任务。
"""
import multiprocessing as mp
import threading
import time
import uuid
from collections import deque


class PoolManager:
    """Worker 进程池

    用法:
        pool = PoolManager()
        pool.start(worker_count=2, use_gpu=True)
        job_id = pool.submit_job({"job_type": "simulate", ...})
        result = pool.get_result(job_id)
        pool.stop()
    """

    def __init__(self, store=None):
        self.store = store
        self.workers = []          # [(process, pipe)]
        self.pending_jobs = deque()
        self.idle_workers = deque()  # [(worker_id, pipe)]

        self._running = False
        self._lock = threading.Lock()
        self._result_thread = None

        # 任务状态
        self.job_statuses = {}  # job_id -> {"status": str, "progress": int, ...}
        self.job_sessions = {}  # job_id -> session_id
        self.worker_jobs = {}   # worker_id -> job_id

        # 配置
        self.config = {
            "worker_count": 1,
            "use_gpu": True,
            "max_iterations": 20000,
        }

        # 状态变更回调 (WebSocket 推送用)
        self.on_status_change = None  # callable(job_id, status)

    def start(self, worker_count=None, use_gpu=None):
        """启动 Worker 池"""
        if self._running:
            return

        if worker_count is not None:
            self.config["worker_count"] = worker_count
        if use_gpu is not None:
            self.config["use_gpu"] = use_gpu

        self._running = True
        self._spawn_workers()
        self._result_thread = threading.Thread(target=self._result_loop, daemon=True)
        self._result_thread.start()

    def _spawn_workers(self):
        for i in range(self.config["worker_count"]):
            parent_pipe, child_pipe = mp.Pipe()
            proc = mp.Process(
                target=_worker_entry,
                args=(child_pipe, i, self.config["use_gpu"]),
                daemon=True,
            )
            proc.start()
            child_pipe.close()
            self.workers.append((proc, parent_pipe))
            self.idle_workers.append((i, parent_pipe))

    def submit_job(self, job_data):
        """提交任务，返回 job_id"""
        job_id = str(uuid.uuid4())
        job_data = dict(job_data)
        job_data["job_id"] = job_id

        with self._lock:
            self.job_statuses[job_id] = {"status": "queued", "progress": 0}
            self.job_sessions[job_id] = job_data.get("session_id", "")
            self.pending_jobs.append(job_data)

        self._dispatch()
        return job_id

    def _dispatch(self):
        """尝试将待办任务分配给空闲 worker"""
        while self.idle_workers and self.pending_jobs:
            wid, pipe = self.idle_workers.popleft()
            job = self.pending_jobs.popleft()
            job_id = job["job_id"]

            with self._lock:
                self.job_statuses[job_id]["status"] = "running"
                self.worker_jobs[wid] = job_id

            pipe.send(job)

            if self.on_status_change:
                self.on_status_change(job_id, "running")

    def _result_loop(self):
        """监听所有 worker 的结果管道（后台线程）"""
        while self._running:
            for wid, (proc, pipe) in list(enumerate(self.workers)):
                if not proc.is_alive():
                    # Worker 进程已死，清理
                    with self._lock:
                        job_id = self.worker_jobs.pop(wid, None)
                        if job_id and job_id in self.job_statuses:
                            self.job_statuses[job_id]["status"] = "error"
                            self.job_statuses[job_id]["error"] = f"Worker {wid} 意外退出"
                    self._recover_worker(wid)
                    continue
                try:
                    if not pipe.poll(0.01):
                        continue
                except (EOFError, OSError, BrokenPipeError):
                    self._recover_worker(wid)
                    continue
                try:
                    msg = pipe.recv()
                except (EOFError, OSError):
                    continue

                msg_type = msg.get("type")
                job_id = msg.get("job_id")

                if msg_type == "progress":
                    with self._lock:
                        if job_id in self.job_statuses:
                            self.job_statuses[job_id]["progress"] = msg["progress"]

                elif msg_type == "result":
                    result = msg["result"]
                    with self._lock:
                        self.job_statuses[job_id]["status"] = "completed"
                        self.job_statuses[job_id]["progress"] = 100
                        sid = self.job_sessions.get(job_id, "")
                    if self.store:
                        self.store.put(job_id, result, sid)
                    if self.on_status_change:
                        self.on_status_change(job_id, "completed")

                    # 回收 worker
                    with self._lock:
                        self.worker_jobs.pop(wid, None)
                    self.idle_workers.append((wid, pipe))
                    self._dispatch()

                elif msg_type == "error":
                    with self._lock:
                        self.job_statuses[job_id]["status"] = "error"
                        self.job_statuses[job_id]["error"] = msg.get("error", "")
                    if self.on_status_change:
                        self.on_status_change(job_id, "error")

                    with self._lock:
                        self.worker_jobs.pop(wid, None)
                    self.idle_workers.append((wid, pipe))
                    self._dispatch()

    def get_result(self, job_id):
        """获取任务结果"""
        if self.store:
            return self.store.get(job_id)
        return None

    def get_job_status(self, job_id):
        """获取任务状态"""
        with self._lock:
            s = self.job_statuses.get(job_id)
            if s is None:
                return None
            return dict(s)

    def get_session_jobs(self, session_id):
        """获取某 session 的所有任务"""
        with self._lock:
            return [{"job_id": jid, **self.job_statuses[jid]}
                    for jid, sid in self.job_sessions.items()
                    if sid == session_id]

    def cancel_job(self, job_id):
        """取消排队中的任务"""
        with self._lock:
            for i, job in enumerate(self.pending_jobs):
                if job["job_id"] == job_id:
                    self.pending_jobs.remove(job)
                    self.job_statuses[job_id]["status"] = "cancelled"
                    if self.on_status_change:
                        self.on_status_change(job_id, "cancelled")
                    return True
            return False

    def get_workers_status(self):
        """获取所有 worker 状态"""
        result = []
        with self._lock:
            for wid, (proc, _) in enumerate(self.workers):
                job_id = self.worker_jobs.get(wid)
                status = "busy" if job_id else "idle"
                progress = self.job_statuses[job_id]["progress"] if job_id and job_id in self.job_statuses else None
                result.append({
                    "id": wid,
                    "status": status,
                    "job_id": job_id,
                    "progress": progress,
                })
        return result

    def reconfigure(self, new_config):
        """更新配置 (需重启生效)"""
        with self._lock:
            self.config.update(new_config)

    def restart(self):
        """重启 Worker 池"""
        self.stop()
        time.sleep(0.5)
        self.start()

    def stop(self):
        """停止所有 Worker"""
        self._running = False
        for _, pipe in self.workers:
            try:
                pipe.send(None)
            except Exception:
                pass
        for proc, _ in self.workers:
            proc.join(timeout=3)
            if proc.is_alive():
                proc.terminate()
        self.workers.clear()
        self.idle_workers.clear()
        self.worker_jobs.clear()

    def _recover_worker(self, wid):
        """尝试恢复崩溃的 Worker"""
        try:
            proc, pipe = self.workers[wid]
            proc.join(timeout=1)
            if proc.is_alive():
                proc.terminate()
            pipe.close()
        except Exception:
            pass
        # 创建新 worker 替换
        parent_pipe, child_pipe = mp.Pipe()
        proc = mp.Process(
            target=_worker_entry,
            args=(child_pipe, wid, self.config["use_gpu"]),
            daemon=True,
        )
        proc.start()
        child_pipe.close()
        self.workers[wid] = (proc, parent_pipe)
        self.idle_workers.append((wid, parent_pipe))
        print(f"[Pool] Worker {wid} 已恢复")

    def get_queue_length(self):
        """获取待办队列长度"""
        with self._lock:
            return len(self.pending_jobs)

    def get_config(self):
        """获取当前配置"""
        with self._lock:
            return dict(self.config)


def _worker_entry(pipe, worker_id, use_cuda):
    """子进程入口—包装 worker_loop"""
    from server.worker import worker_loop
    worker_loop(pipe, worker_id, use_cuda)
