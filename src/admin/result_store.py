"""结果磁盘缓存：原子写入、TTL/LRU 清理和坏文件隔离。"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path

import numpy as np


ANIMATION_CHUNK_SIZE = 20
ANIMATION_FORMAT = 'float32-chunks-v1'


class ResultStore:
    """仅在内存保存索引，大型图表和动画数据落到磁盘。"""

    def __init__(self, settings, logger=None, cache_dir=None):
        self.settings = settings
        self.log = logger
        self.cache_dir = Path(
            cache_dir or Path(tempfile.gettempdir()) / 'PatternGenerator' / 'result-cache'
        )
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
                        self._discard_file(path)
                        continue
                    envelope = self._read_file(path)
                    client_id = envelope['client_id']
                    cache_type = envelope['cache_type']
                    item = {'task_id': path.stem, 'path': path,
                            'updated_at': path.stat().st_mtime, 'size': self._storage_size(path)}
                    current = self._index.setdefault(client_id, {}).get(cache_type)
                    if current is None or item['updated_at'] > current['updated_at']:
                        self._index[client_id][cache_type] = item
                    elif path.exists():
                        self._discard_file(path)
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

    def _chunk_path(self, path, index):
        return path.with_name(f'{path.stem}.{index:04d}.bin')

    def _storage_size(self, path):
        return path.stat().st_size + sum(
            chunk.stat().st_size for chunk in path.parent.glob(f'{path.stem}.[0-9][0-9][0-9][0-9].bin')
        )

    def _put_chunked_animation(self, client_id, task_id, data, update_index=True):
        """帧按 Float32 分块写入；最后提交小型元数据文件。"""
        animation = data.get('animation')
        frames = animation.get('frames') if isinstance(animation, dict) else None
        if not isinstance(frames, list) or not frames:
            return False
        path = self.cache_dir / f'{task_id}.json'
        temp_path = path.with_suffix('.json.tmp')
        written_chunks = []
        try:
            height = len(frames[0]['x_data'])
            width = len(frames[0]['x_data'][0])
            if not height or not width or len(frames) != animation.get('total_frames'):
                raise ValueError('动画帧结构无效')
            bytes_per_frame = height * width * 2 * 4
            chunk_size = min(ANIMATION_CHUNK_SIZE, self._max_file_bytes() // bytes_per_frame)
            if chunk_size < 1:
                raise ValueError('单帧超过缓存文件大小限制')
            metadata = {key: value for key, value in animation.items() if key != 'frames'}
            metadata.update({
                'format': ANIMATION_FORMAT, 'cache_id': task_id,
                'shape': [height, width], 'chunk_size': chunk_size,
                'chunk_count': (len(frames) + chunk_size - 1) // chunk_size,
            })
            envelope = {
                'client_id': client_id, 'cache_type': 'animation', 'saved_at': time.time(),
                'data': {**data, 'animation': metadata},
            }
            encoded = json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            if len(encoded) > self._max_file_bytes():
                return False
            with self._lock:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                for index, start in enumerate(range(0, len(frames), chunk_size)):
                    group = frames[start:start + chunk_size]
                    values = np.asarray(
                        [[frame['x_data'], frame['y_data']] for frame in group], dtype='<f4'
                    )
                    if values.shape != (len(group), 2, height, width):
                        raise ValueError('动画帧尺寸不一致')
                    chunk_path = self._chunk_path(path, index)
                    chunk_temp = chunk_path.with_suffix('.bin.tmp')
                    with open(chunk_temp, 'wb') as handle:
                        handle.write(values.tobytes(order='C'))
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(chunk_temp, chunk_path)
                    written_chunks.append(chunk_path)
                with open(temp_path, 'wb') as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, path)
                if update_index:
                    self._index.setdefault(client_id, {})['animation'] = {
                        'task_id': task_id, 'path': path,
                        'updated_at': time.time(), 'size': self._storage_size(path),
                    }
                else:
                    current = self._index.get(client_id, {}).get('animation')
                    if current and current['path'] == path:
                        current['size'] = self._storage_size(path)
                self._enforce_limits()
            return path.is_file()
        except (OSError, TypeError, ValueError, KeyError) as exc:
            self._discard_file(temp_path)
            for chunk in written_chunks:
                self._discard_file(chunk)
            if self.log:
                self.log.error_event('cache_result_write_failed', detail={'error': exc})
            return False

    def _prepare_animation(self, path, envelope):
        animation = envelope['data'].get('animation')
        if (envelope['cache_type'] == 'animation' and isinstance(animation, dict)
                and isinstance(animation.get('frames'), list)):
            if self._put_chunked_animation(envelope['client_id'], path.stem, envelope['data'], False):
                return self._read_file(path)
        return envelope

    def put(self, client_id, task_id, cache_type, data):
        """原子写入一份结果，并更新客户端最新结果索引。"""
        if not client_id or cache_type not in ('simulation', 'animation') or not isinstance(data, dict):
            return False
        if cache_type == 'animation':
            return self._put_chunked_animation(client_id, task_id, data)
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
                self.log.error_event('cache_result_write_failed', detail={'error': exc})
            return False

    def get(self, client_id, include_animation=True, include_simulation=True):
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
            if cache_type == 'simulation' and not include_simulation:
                continue
            try:
                envelope = self._prepare_animation(item['path'], self._read_file(item['path']))
                result['anim' if cache_type == 'animation' else 'type'] = (
                    envelope['data'] if cache_type == 'animation' else envelope['data'].get('type', 'simulation'))
                if cache_type == 'simulation':
                    result.update(envelope['data'])
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                with self._lock:
                    self._index.get(client_id, {}).pop(cache_type, None)
                self._discard_file(item['path'])
        return result or None

    def get_task(self, client_id, task_id):
        """按任务 ID 读取已落盘结果，供任务完成后的首次结果交付使用。"""
        if not client_id or not task_id or Path(task_id).name != task_id:
            return None
        path = self.cache_dir / f'{task_id}.json'
        try:
            envelope = self._read_file(path)
            if envelope['client_id'] != client_id:
                return None
            return self._prepare_animation(path, envelope)['data']
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self._discard_file(path)
            return None

    def get_animation_chunk(self, client_id, task_id, index):
        """只返回已认证客户端所属缓存的一块原始 Float32 帧。"""
        if (not client_id or not task_id or Path(task_id).name != task_id
                or '.' in task_id or not 0 <= index < 1000):
            return None
        path = self.cache_dir / f'{task_id}.json'
        try:
            envelope = self._read_file(path)
            animation = envelope['data'].get('animation', {})
            if (envelope['client_id'] != client_id or envelope['cache_type'] != 'animation'
                    or animation.get('format') != ANIMATION_FORMAT
                    or index >= animation['chunk_count']):
                return None
            frame_count = min(animation['chunk_size'], animation['total_frames'] - index * animation['chunk_size'])
            height, width = animation['shape']
            chunk_path = self._chunk_path(path, index)
            if chunk_path.stat().st_size != frame_count * 2 * height * width * 4:
                return None
            return chunk_path.read_bytes()
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def remove_client(self, client_id):
        with self._lock:
            entries = self._index.pop(client_id, {})
            removed = bool(entries)
            for item in entries.values():
                self._discard_file(item['path'])
            return removed

    def clear(self):
        with self._lock:
            paths = (list(self.cache_dir.glob('*.json')) + list(self.cache_dir.glob('*.bin'))
                     + list(self.cache_dir.glob('*.tmp')))
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
            for path in list(self.cache_dir.glob('*.bin')):
                if not (self.cache_dir / f'{path.name.rsplit(".", 2)[0]}.json').exists():
                    self._discard_file(path)
            for path in list(self.cache_dir.glob('*.json')):
                try:
                    if now - path.stat().st_mtime > self._ttl_seconds():
                        self._discard_file(path)
                except OSError:
                    pass
            for client_id, entries in list(self._index.items()):
                for cache_type, item in list(entries.items()):
                    try:
                        if not item['path'].exists() or now - item['updated_at'] > self._ttl_seconds():
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
                    size = self._storage_size(path)
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
            path = Path(path)
            if path.suffix == '.json':
                for chunk in path.parent.glob(f'{path.stem}.[0-9][0-9][0-9][0-9].bin'):
                    chunk.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
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
                    self.log.error_event('cache_result_cleanup_failed', detail={'exception': type(exc).__name__})
