"""异步任务队列 - FIFO 调度、取消、超时、重试、死信、多 GPU、显存预检

状态机：queued → running → completed / cancelled / timeout / failed
- 失败（非取消/超时）自动重试：重试期间状态回到 queued（retry_count 递增）。
- 重试耗尽的终态失败任务 status='failed' 并进入死信队列（dead list），可手动重试或删除。
- 暂停冻结：客户端 paused 时其任务保留队列位置但跳过执行，恢复后继续。
- 结果生命周期：取走即释放；未取走的按 task_result_ttl_minutes 到期释放（标记 expired）。

task_fn 契约：接收 Task，返回可 JSON 序列化的结果 dict；
取消时抛出 tasks.TaskCancelled（由 web 层把 core.simulation.SimulationCancelled 翻译为本异常）。
"""

import re
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from core.simulation import estimate_host_ram_mb, estimate_vram_mb

FINISHED_STATUSES = ('completed', 'cancelled', 'timeout', 'failed', 'expired')
_HISTORY_LIMIT = 500


class TaskCancelled(Exception):
    """任务取消信号：task_fn 捕获 core 的 SimulationCancelled 后翻译抛出"""
    pass


class QueueLimitError(Exception):
    """任务队列达到配置上限。"""
    pass


class Task:
    # 任务命名结构：模型-时间(YYYYMMDD-HHMMSS)-4位随机码
    # （随机码保证同一秒提交同模型任务时 task_id 唯一）
    _ID_SAFE_RE = re.compile(r'[^\w一-鿿-]+')

    @classmethod
    def _generate_id(cls, model):
        name = cls._ID_SAFE_RE.sub('-', str(model or '').strip()) or 'task'
        return f'{name}-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:4]}'

    def __init__(self, payload, client_id, owner=''):
        self.task_id = self._generate_id(payload.get('model', ''))
        self.payload = payload
        self.client_id = client_id
        self.owner = owner
        self.type = payload.get('type', 'simulate')
        self.model = payload.get('model', '')
        self.iterations = payload.get('iterations')
        self.frames = payload.get('frames')
        self.status = 'queued'
        self.progress = 0
        self.created_at = time.time()
        self.started_at = None
        self.completed_at = None
        self.retry_count = 0
        self.gpu_id = None
        self.estimated_vram_mb = estimate_vram_mb()
        self.estimated_ram_mb = estimate_host_ram_mb(self.frames or 0)
        self.result = None
        self.error = None
        self.delivered = False
        self.by = None  # 取消来源：client / admin
        self.cancel_event = threading.Event()
        self._timeout_flag = False
        self._lock = threading.RLock()

    def snapshot(self, include_result=False):
        with self._lock:
            data = {
                'task_id': self.task_id,
                'client_id': self.client_id,
                'type': self.type,
                'model': self.model,
                'iterations': self.iterations,
                'frames': self.frames,
                'status': self.status,
                'progress': self.progress,
                'created_at': self.created_at,
                'started_at': self.started_at,
                'completed_at': self.completed_at,
                'retry_count': self.retry_count,
                'gpu_id': self.gpu_id,
                'estimated_vram_mb': self.estimated_vram_mb,
                'estimated_ram_mb': self.estimated_ram_mb,
                'error': self.error,
                'delivered': self.delivered,
                'by': self.by,
            }
            if include_result:
                data['result'] = self.result
            return data

    def set_progress(self, percent):
        with self._lock:
            if percent > self.progress:
                self.progress = min(100, int(percent))
                return self.progress
            return None

    def finish(self, status, error=None):
        with self._lock:
            self.status = status
            self.error = error
            self.completed_at = time.time()


class TaskQueue:
    def __init__(self, logger, settings, clients, monitor, notifier=None, task_fn=None):
        self.log = logger
        self.settings = settings
        self.clients = clients
        self.monitor = monitor
        self.notifier = notifier
        self.task_fn = task_fn

        self._tasks = {}          # task_id -> Task（全部已知任务）
        self._waiting = deque()   # 排队中的 task_id
        self._dead = []           # 死信 task_id 列表
        self._order = deque()  # 历史展示顺序；由配置控制并定期裁剪
        self._active = 0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._events = []         # 事件回调列表（WS 推送、通知等注册）

        # use_cuda 判定交给 task_fn 侧；队列只在有 GPU 信息时做显存预检
        self._use_cuda = monitor.gpu_count > 0

    # ---------- 生命周期 ----------

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name='task-queue', daemon=True)
            self._thread.start()

    def stop(self, cancel_running=True):
        """停止调度器；取消所有运行中与排队中的任务后等待收尾"""
        self._stop.set()
        if cancel_running:
            self.cancel_all(by='admin')
        if self._thread is not None:
            self._thread.join(timeout=5)
        executor = getattr(self, '_executor', None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    def on_event(self, callback):
        """注册任务事件回调 callback(event_type, task_snapshot)"""
        self._events.append(callback)

    def _emit(self, event_type, task):
        snapshot = task.snapshot()
        for callback in list(self._events):
            try:
                callback(event_type, snapshot)
            except Exception as e:
                if self.log:
                    self.log.error(f'任务事件回调异常: {e}')

    # ---------- 提交与查询 ----------

    def submit(self, payload, client_id, owner=''):
        task = Task(payload, client_id, owner=owner)
        with self._lock:
            active_count = sum(1 for item in self._tasks.values()
                               if item.status in ('queued', 'running'))
            max_queue = max(1, int(self.settings.get('max_queue_tasks', 100)))
            if active_count >= max_queue:
                raise QueueLimitError('任务队列已达到上限，请稍后再试')
            while task.task_id in self._tasks:  # 同模型同秒撞名时重新生成，保证键唯一
                task.task_id = Task._generate_id(payload.get('model', ''))
            self._tasks[task.task_id] = task
            self._waiting.append(task.task_id)
            self._order.append(task.task_id)
        if self.clients:
            client = self.clients.get(client_id)
            if client:
                client.total_tasks += 1
                self.clients.mark_status(client_id, 'queued', task.task_id)
        self.log.info(f"任务入队: {task.task_id[:8]} {task.type} {task.model} by {client_id[:8]}")
        self._emit('created', task)
        return task

    def get(self, task_id, include_result=False):
        with self._lock:
            task = self._tasks.get(task_id)
        return task.snapshot(include_result=include_result) if task else None

    def get_task(self, task_id):
        with self._lock:
            return self._tasks.get(task_id)

    def queue_position(self, task_id):
        with self._lock:
            if task_id in self._waiting:
                return list(self._waiting).index(task_id) + 1
            return 0

    def counts(self):
        with self._lock:
            waiting = sum(1 for tid in self._waiting if self._tasks[tid].status == 'queued')
            running = sum(1 for t in self._tasks.values() if t.status == 'running')
            return {'waiting': waiting, 'running': running}

    def _list_by(self, pred):
        with self._lock:
            tasks = [self._tasks[tid] for tid in self._order if tid in self._tasks and pred(self._tasks[tid])]
        return [t.snapshot() for t in tasks]

    def list_waiting(self):
        return self._list_by(lambda t: t.status == 'queued')

    def list_running(self):
        return self._list_by(lambda t: t.status == 'running')

    def list_history(self):
        return self._list_by(lambda t: t.status in FINISHED_STATUSES)

    def list_dead(self):
        with self._lock:
            tasks = [self._tasks[tid] for tid in self._dead if tid in self._tasks]
        return [t.snapshot() for t in tasks]

    # ---------- 取消 / 重试 / 队列管理 ----------

    def cancel(self, task_id, by='client'):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False, 'not_found'
            if task.status == 'queued':
                try:
                    self._waiting.remove(task_id)
                except ValueError:
                    pass
                task.by = by
                task.finish('cancelled', '排队中被取消')
                if self.clients:
                    self.clients.record_task_result(task.client_id, 'cancelled')
                    self.clients.mark_status(task.client_id, 'online')
                self.log.info(f"任务取消: {task_id[:8]} ({by})")
                self._emit('cancelled', task)
                self._prune_records()
                return True, 'cancelled'
            if task.status == 'running':
                task.by = by
                task.cancel_event.set()
                self.log.info(f"任务取消请求: {task_id[:8]} ({by}，等待迭代边界退出)")
                return True, 'cancelling'
            return False, f'bad_status:{task.status}'

    def cancel_all(self, by='admin'):
        with self._lock:
            ids = list(self._waiting) + [t.task_id for t in self._tasks.values() if t.status == 'running']
        for task_id in ids:
            self.cancel(task_id, by=by)

    def cancel_client_tasks(self, client_id, by='admin'):
        """取消某客户端的运行中任务并移除其排队任务（暂停/踢出用），返回处理数"""
        count = 0
        with self._lock:
            running = [t.task_id for t in self._tasks.values()
                       if t.client_id == client_id and t.status == 'running']
            queued = [tid for tid in self._waiting if self._tasks[tid].client_id == client_id]
        for task_id in running:
            self.cancel(task_id, by=by)
            count += 1
        for task_id in queued:
            task = self._tasks.get(task_id)
            if task and task.status == 'queued':
                try:
                    self._waiting.remove(task_id)
                except ValueError:
                    pass
                task.by = by
                task.finish('cancelled', '客户端被暂停或踢出')
                if self.clients:
                    self.clients.record_task_result(client_id, 'cancelled')
                self._emit('cancelled', task)
                self._prune_records()
                count += 1
        return count

    def clear_queue(self):
        with self._lock:
            queued = [tid for tid in self._waiting if self._tasks[tid].status == 'queued']
            for tid in queued:
                self._waiting.remove(tid)
                task = self._tasks[tid]
                task.finish('cancelled', '队列被清空')
                if self.clients:
                    self.clients.record_task_result(task.client_id, 'cancelled')
                    self.clients.mark_status(task.client_id, 'online')
        for tid in queued:
            self._emit('cancelled', self._tasks[tid])
        self._prune_records()
        return len(queued)

    def retry(self, task_id):
        """重试失败（死信）任务：计数清零重新排队"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != 'failed':
                return False
            if task_id in self._dead:
                self._dead.remove(task_id)
            task.retry_count = 0
            task.error = None
            task.status = 'queued'
            task.created_at = time.time()
            self._waiting.append(task.task_id)
        self.log.info(f"死信重试: {task_id[:8]}")
        self._emit('created', task)
        return True

    def remove_dead(self, task_id):
        with self._lock:
            if task_id in self._dead:
                self._dead.remove(task_id)
            task = self._tasks.pop(task_id, None)
            if task:
                try:
                    self._order.remove(task_id)
                except ValueError:
                    pass
            return task is not None

    def mark_delivered(self, task_id):
        """结果已被客户端取走：置位 delivered 并释放结果内存"""
        with self._lock:
            task = self._tasks.get(task_id)
        if task and task.status == 'completed':
            with task._lock:
                task.delivered = True
                task.result = None
        self._prune_records()

    def _prune_records(self):
        """裁剪已无结果引用的历史和超限死信，避免任务字典无限增长。"""
        with self._lock:
            max_history = max(1, int(self.settings.get('max_history_tasks', _HISTORY_LIMIT)))
            history_ids = [tid for tid in self._order
                           if tid in self._tasks and self._tasks[tid].status in FINISHED_STATUSES]
            for task_id in history_ids[:-max_history]:
                task = self._tasks.get(task_id)
                if task is not None and (task.result is None or task.delivered):
                    self._tasks.pop(task_id, None)
                    try:
                        self._order.remove(task_id)
                    except ValueError:
                        pass

            max_dead = max(1, int(self.settings.get('max_dead_tasks', 100)))
            while len(self._dead) > max_dead:
                old_id = self._dead.pop(0)
                old_task = self._tasks.get(old_id)
                if old_task is not None and old_task.result is None:
                    self._tasks.pop(old_id, None)
                    try:
                        self._order.remove(old_id)
                    except ValueError:
                        pass

    # ---------- 调度循环 ----------

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._reap_timeouts()
                self._expire_results()
                self._try_dispatch()
            except Exception as e:
                self.log.error(f'调度循环异常: {e}')
            self._stop.wait(0.2)

    def _concurrency(self):
        return max(1, int(self.settings.get('max_compute_concurrency', 1)))

    def _timeout(self):
        return max(10, int(self.settings.get('task_timeout_seconds', 300)))

    def _reserve_mb(self):
        return max(0, int(self.settings.get('gpu_memory_reserve_mb', 512)))

    def _reap_timeouts(self):
        now = time.time()
        limit = self._timeout()
        with self._lock:
            running = [t for t in self._tasks.values() if t.status == 'running']
        for task in running:
            if task.started_at and now - task.started_at > limit and not task._timeout_flag:
                task._timeout_flag = True
                task.cancel_event.set()
                self.log.warning(f"任务超时: {task.task_id[:8]} 超过 {limit}s")

    def _expire_results(self):
        ttl = max(1, int(self.settings.get('task_result_ttl_minutes', 30))) * 60
        now = time.time()
        with self._lock:
            expired = [
                t for t in self._tasks.values()
                if t.status == 'completed' and not t.delivered and t.result is not None
                and t.completed_at and now - t.completed_at > ttl
            ]
        for task in expired:
            with task._lock:
                if task.result is not None:
                    task.result = None
                    task.status = 'expired'
            self.log.info(f"任务结果过期释放: {task.task_id[:8]}")
        if expired:
            self._prune_records()

    def _try_dispatch(self):
        with self._lock:
            if self._active >= self._concurrency():
                return
            task = None
            for tid in self._waiting:
                candidate = self._tasks[tid]
                if candidate.status != 'queued':
                    continue
                client = self.clients.get(candidate.client_id) if self.clients else None
                if client is not None and client.status == 'paused':
                    continue  # 暂停冻结：保留队列位置但跳过
                task = candidate
                break
            if task is None:
                return

            # 显存预检查：空闲显存不足则等待（FIFO 阻塞后续任务）
            if self._use_cuda and self.monitor is not None:
                gpu_id = self.monitor.pick_best_gpu()
                free = self.monitor.gpu_free_mb(gpu_id)
                if free is not None and free < task.estimated_vram_mb + self._reserve_mb():
                    return
                task.gpu_id = gpu_id
            else:
                task.gpu_id = None

            self._waiting.remove(task.task_id)
            task.status = 'running'
            task.started_at = time.time()
            self._active += 1
        if self.clients:
            self.clients.mark_status(task.client_id, 'computing', task.task_id)
        self._emit('running', task)
        executor = self._get_executor()
        executor.submit(self._run_task, task)

    def _get_executor(self):
        workers = self._concurrency()
        if getattr(self, '_executor_workers', None) != workers or getattr(self, '_executor', None) is None:
            old = getattr(self, '_executor', None)
            if old is not None:
                old.shutdown(wait=False)
            self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='task')
            self._executor_workers = workers
        return self._executor

    def _run_task(self, task):
        try:
            self.log.info(f"任务开始: {task.task_id[:8]} {task.type} {task.model}"
                          + (f" GPU{task.gpu_id}" if task.gpu_id is not None else ""))
            result = self.task_fn(task)
            with task._lock:
                task.result = result
            task.finish('completed')
            if self.clients:
                self.clients.record_task_result(task.client_id, 'success', task.completed_at - task.started_at)
                self.clients.mark_status(task.client_id, 'online')
            self.log.info(f"任务完成: {task.task_id[:8]} 耗时 {task.completed_at - task.started_at:.1f}s")
            self._emit('completed', task)
        except TaskCancelled:
            status = 'timeout' if task._timeout_flag else 'cancelled'
            task.finish(status, '执行超时' if task._timeout_flag else '被取消')
            if self.clients:
                self.clients.record_task_result(task.client_id, 'cancelled', task.completed_at - task.started_at)
                self.clients.mark_status(task.client_id, 'online')
            self.log.info(f"任务{status}: {task.task_id[:8]}")
            self._emit(status, task)
        except Exception as e:
            self.log.error(f"任务失败: {task.task_id[:8]} {e}")
            max_retries = max(0, int(self.settings.get('task_retry_count', 1)))
            if task.retry_count < max_retries:
                task.retry_count += 1
                task.status = 'queued'
                task.progress = 0
                task.cancel_event.clear()
                task._timeout_flag = False
                task.started_at = None
                with self._lock:
                    self._waiting.append(task.task_id)
                self.log.info(f"任务重试: {task.task_id[:8]} 第 {task.retry_count}/{max_retries} 次")
                self._emit('retry', task)
                if self.notifier:
                    self.notifier.notify(
                        'task_failed',
                        f'{task.task_id[:8]} {task.model} 失败，正在重试',
                    )
            else:
                task.finish('failed', str(e))
                with self._lock:
                    self._dead.append(task.task_id)
                if self.clients:
                    self.clients.record_task_result(task.client_id, 'failed', task.completed_at - task.started_at)
                    self.clients.mark_status(task.client_id, 'online')
                self.log.info(f"任务进入死信: {task.task_id[:8]}")
                self._emit('dead', task)
                if self.notifier:
                    self.notifier.notify(
                        'task_failed',
                        f'{task.task_id[:8]} {task.model} 失败，已进入死信队列',
                    )
        finally:
            self._prune_records()
            with self._lock:
                self._active = max(0, self._active - 1)
