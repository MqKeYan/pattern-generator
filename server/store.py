"""
结果存储模块
==========
内存 + 文件两级结果缓存，带 TTL 过期和 session 配额管理。
"""
import time
import os
import threading
import json

_temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp", "results")


class ResultStore:
    """任务结果存储

    小结果 (< 10MB) 保持在内存，大结果写入文件。
    TTL 1 小时后自动清理。每个 session 最多保留 20 条记录。

    用法:
        store = ResultStore()
        store.put("job-xxx", {"x_data": [...]})
        result = store.get("job-xxx")
    """

    def __init__(self, ttl_seconds=3600):
        self.ttl = ttl_seconds
        self._cache = {}        # job_id -> {data, timestamp, session_id, size}
        self._sessions = {}     # session_id -> [job_id, ...]
        self._lock = threading.Lock()

        os.makedirs(_temp_dir, exist_ok=True)

        # 后台清理线程
        self._cleaner = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleaner.start()

    def put(self, job_id, data, session_id):
        """存储任务结果"""
        size = _estimate_size(data)
        entry = {
            "data": data,
            "timestamp": time.time(),
            "session_id": session_id,
            "size": size,
            "on_disk": False,
        }

        with self._lock:
            # 大结果写入文件
            if size > 10 * 1024 * 1024:
                filepath = os.path.join(_temp_dir, f"{job_id}.json")
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                entry["data"] = None  # 释放内存
                entry["filepath"] = filepath
                entry["on_disk"] = True

            self._cache[job_id] = entry

            # session 配额管理
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            self._sessions[session_id].append(job_id)
            if len(self._sessions[session_id]) > 20:
                old_job = self._sessions[session_id].pop(0)
                self._delete(old_job)

    def get(self, job_id):
        """获取任务结果"""
        with self._lock:
            entry = self._cache.get(job_id)
            if entry is None:
                return None
            entry["timestamp"] = time.time()  # 刷新 TTL
            if entry["on_disk"]:
                with open(entry["filepath"], "r", encoding="utf-8") as f:
                    return json.load(f)
            return entry["data"]

    def delete(self, job_id):
        """删除任务结果"""
        with self._lock:
            self._delete(job_id)

    def _delete(self, job_id):
        entry = self._cache.pop(job_id, None)
        if entry and entry.get("on_disk"):
            try:
                os.remove(entry["filepath"])
            except OSError:
                pass

    def _cleanup_loop(self):
        while True:
            time.sleep(60)
            now = time.time()
            with self._lock:
                expired = [jid for jid, e in self._cache.items()
                           if now - e["timestamp"] > self.ttl]
                for jid in expired:
                    self._delete(jid)


def _estimate_size(data):
    """估算数据大小（字节）"""
    try:
        return len(json.dumps(data, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0
