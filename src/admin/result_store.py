"""结果磁盘缓存：原子写入、TTL/LRU 清理和坏文件隔离。"""

import json
import os
import threading
import time
from pathlib import Path
from paths import software_root


SOFTWARE_ROOT = software_root()


class ResultStore:
    """仅在内存保存索引，大型图表和动画数据落到磁盘。"""

    def __init__(self, settings, logger=None, cache_dir=None):
        self.settings = settings
        self.log = logger
        self.cache_dir = Path(cache_dir or SOFTWARE_ROOT / 'temp' / 'result-cache')
        self._lock = threading.RLock()
        self._index = {}
        self._stop = threading.Event()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cleanup()
        self._load_index()
        self._thread = threading.Thread(target=self._cleanup_loop, name='result-cache-cleaner', daemon=True)
        self._thread.start()

    def _ttl_seconds(self):
        return max(1, int(self.settings.get('task_result_ttl_minutes', 30))) * 60

    def _max_bytes(self):
        return max(1, int(self.settings.get('max_cache_mb', 1024))) * 1024 * 1024

    def _max_file_bytes(self):
        return max(1, int(self.settings.get('max_cache_file_mb', 256))) * 1024 * 1024

    def _load_index(self):
        """启动时扫描缓存；坏文件或过期文件只删除缓存项。"""
        now = time.time()
        with self._lock:
            for path in self.cache_dir.glob('*.json'):
                try:
                    if now - path.stat().st_mtime > self._ttl_seconds():
                        path.unlink(missing_ok=True)
                        continue
                    envelope = self._read_file(path)
                    client_id = envelope['client_id']
                    cache_type = envelope['cache_type']
                    item = {'task_id': path.stem, 'path': path,
                            'updated_at': path.stat().st_mtime, 'size': path.stat().st_size}
                    current = self._index.setdefault(client_id, {}).get(cache_type)
                    if current is None or item['updated_at'] > current['updated_at']:
                        self._index[client_id][cache_type] = item
                    elif path.exists():
                        path.unlink()
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                    self._discard_file(path)
        self._enforce_limits()

    def _read_file(self, path):
        if not path.is_file() or path.stat().st_size > self._max_file_bytes():
            raise ValueError('缓存文件无效')
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('client_id'), str):
            raise ValueError('缓存结构无效')
        if data.get('cache_type') not in ('simulation', 'animation'):
            raise ValueError('缓存类型无效')
        if not isinstance(data.get('data'), dict):
            raise ValueError('缓存数据无效')
        return data

    def put(self, client_id, task_id, cache_type, data):
        """原子写入一份结果，并更新客户端最新结果索引。"""
        if not client_id or cache_type not in ('simulation', 'animation') or not isinstance(data, dict):
            return False
        path = self.cache_dir / f'{task_id}.json'
        envelope = {
            'client_id': client_id,
            'cache_type': cache_type,
            'saved_at': time.time(),
            'data': data,
        }
        temp_path = path.with_suffix('.json.tmp')
        try:
            encoded = json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            if len(encoded) > self._max_file_bytes():
                return False
            with self._lock:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                with open(temp_path, 'wb') as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, path)
                self._index.setdefault(client_id, {})[cache_type] = {
                    'task_id': task_id, 'path': path,
                    'updated_at': time.time(), 'size': len(encoded),
                }
                self._enforce_limits()
            return True
        except (OSError, TypeError, ValueError) as exc:
            self._discard_file(temp_path)
            if self.log:
                self.log.error(f'结果缓存写入失败: {exc}')
            return False

    def get(self, client_id, include_animation=True):
        """读取客户端最新结果；损坏项只删除自身。"""
        if not client_id:
            return None
        result = {}
        with self._lock:
            self.cleanup()
            entries = dict(self._index.get(client_id, {}))
        for cache_type, item in entries.items():
            if cache_type == 'animation' and not include_animation:
                continue
            try:
                envelope = self._read_file(item['path'])
                result['anim' if cache_type == 'animation' else 'type'] = (
                    envelope['data'] if cache_type == 'animation' else envelope['data'].get('type', 'simulation'))
                if cache_type == 'simulation':
                    result.update(envelope['data'])
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                with self._lock:
                    self._index.get(client_id, {}).pop(cache_type, None)
                self._discard_file(item['path'])
        return result or None

    def remove_client(self, client_id):
        with self._lock:
            entries = self._index.pop(client_id, {})
            removed = bool(entries)
            for item in entries.values():
                self._discard_file(item['path'])
            return removed

    def clear(self):
        with self._lock:
            paths = list(self.cache_dir.glob('*.json')) + list(self.cache_dir.glob('*.tmp'))
            self._index.clear()
            for path in paths:
                self._discard_file(path)

    def cleanup(self):
        """清理过期、临时和超限缓存。"""
        now = time.time()
        with self._lock:
            for path in list(self.cache_dir.glob('*.tmp')):
                try:
                    if now - path.stat().st_mtime > 300:
                        path.unlink(missing_ok=True)
                except OSError:
                    pass
            for client_id, entries in list(self._index.items()):
                for cache_type, item in list(entries.items()):
                    try:
                        if now - item['updated_at'] > self._ttl_seconds():
                            self._discard_file(item['path'])
                            entries.pop(cache_type, None)
                    except OSError:
                        entries.pop(cache_type, None)
                if not entries:
                    self._index.pop(client_id, None)
        self._enforce_limits()

    def _enforce_limits(self):
        with self._lock:
            files = []
            total = 0
            for path in self.cache_dir.glob('*.json'):
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                files.append((path.stat().st_mtime, path, size))
                total += size
            max_files = max(1, int(self.settings.get('max_cache_files', 2048)))
            files.sort()
            while total > self._max_bytes() or len(files) > max_files:
                _, path, size = files.pop(0)
                self._discard_file(path)
                total -= size
                for client_id, entries in list(self._index.items()):
                    for cache_type, item in list(entries.items()):
                        if item['path'] == path:
                            entries.pop(cache_type, None)
                    if not entries:
                        self._index.pop(client_id, None)

    def _discard_file(self, path):
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass

    def stop(self):
        """停止定时清理线程。"""
        self._stop.set()
        if getattr(self, '_thread', None) is not None:
            self._thread.join(timeout=2)

    def _cleanup_loop(self):
        while not self._stop.wait(60):
            try:
                self.cleanup()
            except Exception as exc:
                if self.log:
                    self.log.error(f'结果缓存清理失败: {type(exc).__name__}')
