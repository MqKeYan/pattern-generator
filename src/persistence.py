"""本地 JSON 文件的安全读写辅助函数。"""

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path


_WRITE_LOCK = threading.RLock()


def atomic_write_json(path, data):
    """同目录临时文件写入并原子替换，避免中断留下半个 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    encoded = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    with _WRITE_LOCK:
        try:
            with open(temp, 'wb') as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def backup_corrupt_file(path):
    """为无法解析的旧文件保留带时间戳副本。"""
    path = Path(path)
    if not path.is_file():
        return None
    backup = path.with_name(f'{path.stem}.bad-{time.strftime("%Y%m%d-%H%M%S")}{path.suffix}')
    try:
        shutil.copy2(path, backup)
        return backup
    except OSError:
        return None
