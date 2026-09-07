"""客户端管理器 - 追踪客户端状态、统计与持久化

- 统计写入 config/stats.json 永久保留（每 30 秒定时 + 退出时落盘），可后台手动清除。
- 5 分钟无活动自动标记 offline。
- 状态机：online / offline / paused / computing / queued
"""

import json
import threading
import time
from pathlib import Path
from common.persistence import atomic_write_json, backup_corrupt_file
from common.config import software_root

SOFTWARE_ROOT = software_root()
STATS_PATH = SOFTWARE_ROOT / 'config' / 'stats.json'

OFFLINE_AFTER_SECONDS = 5 * 60

# 持久化字段（stats.json 中保留的客户端字段）
_PERSIST_FIELDS = (
    'client_name', 'ip', 'first_seen', 'total_requests', 'total_tasks',
    'total_compute_time', 'success_count', 'failed_count', 'cancelled_count',
    'tags', 'remark',
)


class Client:
    def __init__(self, client_id, client_name='', ip=''):
        self.client_id = client_id
        self.client_name = client_name
        self.ip = ip
        self.first_seen = time.time()
        self.last_seen = self.first_seen
        self.status = 'online'
        self.current_task_id = None
        self.sessions = {}
        self.websocket_sessions = set()
        self.total_requests = 0
        self.total_tasks = 0
        self.total_compute_time = 0.0
        self.success_count = 0
        self.failed_count = 0
        self.cancelled_count = 0
        self.tags = []
        self.remark = ''

    def to_dict(self):
        return {
            'client_id': self.client_id,
            'client_name': self.client_name,
            'ip': self.ip,
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
            'status': self.status,
            'current_task_id': self.current_task_id,
            'total_requests': self.total_requests,
            'total_tasks': self.total_tasks,
            'total_compute_time': round(self.total_compute_time, 2),
            'online_duration_seconds': round(max(0, self.last_seen - self.first_seen)),
            'success_count': self.success_count,
            'failed_count': self.failed_count,
            'cancelled_count': self.cancelled_count,
            'tags': list(self.tags),
            'remark': self.remark,
        }


    def reset_counters(self):
        """清零本客户端的累计计数，保留身份、状态、备注标签等信息"""
        self.total_requests = 0
        self.total_tasks = 0
        self.total_compute_time = 0.0
        self.success_count = 0
        self.failed_count = 0
        self.cancelled_count = 0


class ClientManager:
    SWEEP_INTERVAL_SECONDS = 30

    def __init__(self, logger=None, stats_path=STATS_PATH, settings=None):
        self.log = logger
        self.settings = settings or {}
        self.stats_path = Path(stats_path)
        self._clients = {}
        self._lock = threading.RLock()
        self._peaks = {}
        self._stop_sweep = threading.Event()
        self._sweep_thread = None
        self._load()
        self._start_sweep_loop()

    # ---------- 注册与查询 ----------

    def register_or_touch(self, client_id, client_name='', ip='', session_id=None, websocket=False):
        """注册新客户端或更新活跃时间，返回 Client"""
        if not client_id:
            return None
        session_id = session_id or client_id
        now = time.time()
        with self._lock:
            client = self._clients.get(client_id)
            if client is None:
                max_clients = max(1, int(self.settings.get('max_clients', 1024)))
                if len(self._clients) >= max_clients:
                    if self.log:
                        self.log.warning('客户端数量达到上限，拒绝新客户端')
                    return None
                client = Client(client_id, client_name, ip)
                self._clients[client_id] = client
                if self.log:
                    self.log.info(f'新客户端接入: {client_name or client_id} ({ip})')
            client.sessions[session_id] = now
            if websocket:
                client.websocket_sessions.add(session_id)
            client.last_seen = now
            if client.status == 'offline':
                client.status = 'online'
            if client_name:
                client.client_name = client_name
            if ip:
                client.ip = ip
            return client

    def get(self, client_id):
        with self._lock:
            return self._clients.get(client_id)

    def list(self):
        with self._lock:
            return [c.to_dict() for c in self._clients.values()]

    # ---------- 状态机 ----------

    def mark_status(self, client_id, status, task_id=None, force=False):
        with self._lock:
            client = self._clients.get(client_id)
            if client is None:
                return
            # 任务结束不能让已断开页面的客户端重新变为在线。
            if status == 'online' and not force and not client.sessions:
                client.status = 'offline'
                client.current_task_id = None
                return
            # 暂停状态只能由管理员 resume（force=True）解除，任务入队/结束不得覆盖
            if not force and client.status == 'paused' and status in ('online', 'queued'):
                return
            client.status = status
            client.current_task_id = task_id if task_id is not None else (
                client.current_task_id if status in ('computing', 'queued') else None)
            if status in ('online', 'offline'):
                client.current_task_id = None

    def sweep_offline(self):
        """清理超时页面会话，没有活动页面的客户端标记 offline"""
        cutoff = time.time() - OFFLINE_AFTER_SECONDS
        with self._lock:
            for client in self._clients.values():
                client.sessions = {
                    session_id: seen_at for session_id, seen_at in client.sessions.items()
                    if session_id in client.websocket_sessions or seen_at >= cutoff
                }
                client.websocket_sessions.intersection_update(client.sessions)
                if not client.sessions and client.status != 'offline':
                    client.status = 'offline'
                    client.current_task_id = None

    def disconnect(self, client_id, session_id=None):
        """移除页面会话；客户端没有其他页面时立即标记 offline"""
        if not client_id:
            return False
        with self._lock:
            client = self._clients.get(client_id)
            if client is None:
                return False
            client.sessions.pop(session_id or client_id, None)
            client.websocket_sessions.discard(session_id or client_id)
            if not client.sessions:
                client.status = 'offline'
                client.current_task_id = None
                client.last_seen = time.time() - OFFLINE_AFTER_SECONDS - 1
            return True

    def _start_sweep_loop(self):
        """启动守护线程，定期清扫超时未活动的客户端"""
        if self._sweep_thread is not None and self._sweep_thread.is_alive():
            return
        self._stop_sweep.clear()
        self._sweep_thread = threading.Thread(target=self._sweep_loop, name='client-sweep', daemon=True)
        self._sweep_thread.start()

    def _sweep_loop(self):
        while not self._stop_sweep.is_set():
            self._stop_sweep.wait(self.SWEEP_INTERVAL_SECONDS)
            try:
                self.sweep_offline()
            except Exception:
                if self.log:
                    self.log.error('客户端离线清扫失败', exc_info=True)

    def stop(self):
        """停止清扫线程；服务端退出时调用"""
        self._stop_sweep.set()
        if self._sweep_thread is not None and self._sweep_thread.is_alive():
            self._sweep_thread.join(timeout=2)

    # ---------- 统计 ----------

    def record_request(self, client_id):
        with self._lock:
            client = self._clients.get(client_id)
            if client:
                client.total_requests += 1

    def record_task_result(self, client_id, outcome, compute_time=0.0):
        """outcome: success / failed / cancelled"""
        with self._lock:
            client = self._clients.get(client_id)
            if not client:
                return
            if outcome == 'success':
                client.success_count += 1
            elif outcome == 'failed':
                client.failed_count += 1
            elif outcome == 'cancelled':
                client.cancelled_count += 1
            client.total_compute_time += max(0.0, compute_time)

    def set_remark(self, client_id, remark=None, tags=None):
        with self._lock:
            client = self._clients.get(client_id)
            if not client:
                return False
            if remark is not None:
                client.remark = str(remark)[:200]
            if tags is not None and isinstance(tags, list):
                client.tags = [str(t)[:30] for t in tags[:10]]
            return True

    def summary(self):
        """全局汇总（侧边栏状态卡）"""
        with self._lock:
            clients = list(self._clients.values())
            return {
                'total_clients': len(clients),
                'online_clients': sum(1 for c in clients if c.status != 'offline'),
                'total_requests': sum(c.total_requests for c in clients),
                'total_tasks': sum(c.total_tasks for c in clients),
                'total_compute_time': round(sum(c.total_compute_time for c in clients), 1),
            }

    # ---------- 持久化 ----------

    def _load(self):
        try:
            data = json.loads(self.stats_path.read_text(encoding='utf-8'))
        except (OSError, ValueError, json.JSONDecodeError):
            backup_corrupt_file(self.stats_path)
            return
        with self._lock:
            self._peaks = data.get('peaks', {}) if isinstance(data.get('peaks'), dict) else {}
            for client_id, fields in (data.get('clients') or {}).items():
                if not isinstance(fields, dict):
                    continue
                client = Client(client_id)
                client.status = 'offline'  # 重启后一律 offline，等活动恢复
                for field in _PERSIST_FIELDS:
                    if field in fields:
                        setattr(client, field, fields[field])
                self._clients[client_id] = client

    def save(self, peaks=None):
        """落盘客户端统计与资源峰值汇总"""
        with self._lock:
            if peaks is not None:
                self._peaks = peaks
            data = {
                'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'peaks': self._peaks,
                'clients': {
                    c.client_id: {f: getattr(c, f) for f in _PERSIST_FIELDS}
                    for c in self._clients.values()
                },
            }
        try:
            self.stats_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.stats_path, data)
            return True
        except OSError as e:
            if self.log:
                self.log.error(f'统计落盘失败: {e}')
            return False

    def clear_all_stats(self):
        """后台「清除全部统计」：清空客户端记录与峰值，从零累计"""
        with self._lock:
            self._clients.clear()
            self._peaks = {}
        self.save()

    def reset_counters(self):
        """后台「重置计数」：仅清零各客户端的累计计数（请求数、任务数、
        成功/失败/取消数、累计计算时长），保留客户端记录、备注标签与峰值"""
        with self._lock:
            for client in self._clients.values():
                client.reset_counters()
        self.save()

    def delete(self, client_id):
        """后台「删除客户端记录」：仅移除该客户端的统计记录，不封禁、不断开连接；
        若客户端仍在线，下次请求/心跳会重新登记"""
        with self._lock:
            removed = self._clients.pop(client_id, None) is not None
        if removed:
            self.save()
        return removed
