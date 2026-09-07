"""WebSocket 推送 - 周期推送 metrics/clients/tasks，实时推送日志与告警

- 连接在端点内校验 Origin 同源（HTTP 中间件默认不拦截 WebSocket）。
- 推送循环运行于独立 asyncio 任务；数据均取线程安全快照。
"""

import asyncio
import json

import psutil
from fastapi import WebSocket

# 软件进程启动时间（epoch 秒）：运行时长以此为基准，页面刷新不会重新计时
STARTED_AT = psutil.Process().create_time()


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self._needs_full_sync: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.active.append(ws)
            self._needs_full_sync.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self.active:
                self.active.remove(ws)
            self._needs_full_sync.discard(ws)

    async def broadcast(self, payload: dict):
        """向全部连接并发推送单条消息，慢连接超时后自动释放。"""
        await self.broadcast_batches([payload], [payload])

    async def broadcast_batches(self, full_messages, incremental_messages):
        """新连接接收完整状态，已连接客户端仅接收增量状态。"""
        async with self._lock:
            targets = [(ws, ws in self._needs_full_sync) for ws in self.active]

        async def send_batch(ws, messages):
            try:
                for message in messages:
                    text = json.dumps(message, ensure_ascii=False, default=str)
                    await asyncio.wait_for(ws.send_text(text), timeout=1.0)
                return True
            except Exception:
                return False

        results = await asyncio.gather(
            *(send_batch(ws, full_messages if full else incremental_messages)
              for ws, full in targets),
            return_exceptions=False,
        )
        for (ws, full), sent in zip(targets, results):
            if not sent:
                await self.disconnect(ws)
            elif full:
                async with self._lock:
                    self._needs_full_sync.discard(ws)

    async def close_all(self):
        """服务停止时向所有连接发送关闭帧"""
        async with self._lock:
            targets = list(self.active)
            self.active.clear()
            self._needs_full_sync.clear()
        for ws in targets:
            try:
                await ws.close()
            except Exception:
                pass


async def push_loop(manager, app_context, interval=1.0):
    """周期推送循环：metrics + clients + tasks + 增量日志"""
    log = app_context['log']
    monitor = app_context['monitor']
    clients = app_context['clients']
    task_queue = app_context['task_queue']
    notifier = app_context['notifier']

    log_seq = log.replay()[-1]['seq'] if log.replay() else 0

    while True:
        try:
            counts = task_queue.counts()
            full_metrics = {
                'type': 'metrics',
                'started_at': STARTED_AT,
                'current': monitor.get_metrics(),
                'history': monitor.get_history(),
                'peaks': monitor.get_peaks(),
                'counts': counts,
                'clients_summary': clients.summary(),
            }
            incremental_metrics = dict(full_metrics)
            incremental_metrics.pop('history')
            full_clients = {
                'type': 'clients',
                'data': clients.list(),
            }
            full_tasks = {
                'type': 'tasks',
                'running': task_queue.list_running(),
                'waiting': task_queue.list_waiting(),
                'history': task_queue.list_history()[-50:],
                'dead': task_queue.list_dead(),
                'counts': counts,
            }
            incremental_tasks = dict(full_tasks)
            incremental_tasks.pop('history')
            await manager.broadcast_batches(
                [full_metrics, full_clients, full_tasks],
                [incremental_metrics, full_clients, incremental_tasks],
            )
            entries = log.replay(since_seq=log_seq)
            if entries:
                log_seq = entries[-1]['seq']
                await manager.broadcast({'type': 'logs', 'entries': entries, 'file': log.current_file()})
            notifier.check_queue_backlog(counts['waiting'])
        except Exception:
            pass  # 推送失败不影响下一轮
        await asyncio.sleep(interval)


def check_ws_origin(ws: WebSocket, allowed_host: str) -> bool:
    """WS 端点内 Origin 校验（HTTP 中间件不覆盖 WebSocket 连接）"""
    from security import valid_host_and_origin
    return valid_host_and_origin(ws.headers, {allowed_host})
