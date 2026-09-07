"""日志系统 - 每次运行独立写入日志文件，并保留内存回放缓冲

- 文件按启动时间和 PID 命名，本地永久保留；每次运行独立成文件。
- 内存保留最近 1000 条，供新 WebSocket 连接回放。
- 日志格式：[时间] [级别] 消息
"""

import logging
import os
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from paths import software_root

SOFTWARE_ROOT = software_root()
LOG_DIR = SOFTWARE_ROOT / 'log'

_MEMORY_BUFFER_SIZE = 1000


class _MemoryBufferHandler(logging.Handler):
    """保留最近 N 条格式化日志，带自增序号供增量拉取"""

    def __init__(self, capacity):
        super().__init__()
        # 注意：Handler 自带 self.lock（handle() 调 emit() 前已持有），
        # 缓冲区必须用独立命名的锁，避免非重入死锁
        self._buf_lock = threading.Lock()
        self.buffer = deque(maxlen=capacity)
        self.seq = 0

    def emit(self, record):
        try:
            msg = self.format(record)
            with self._buf_lock:
                self.seq += 1
                self.buffer.append({'seq': self.seq, 'message': msg})
        except Exception:
            self.handleError(record)

    def replay(self, since_seq=0):
        with self._buf_lock:
            return [entry for entry in self.buffer if entry['seq'] > since_seq]


class _RunFileHandler(logging.Handler):
    """为每次软件运行创建独立日志文件（线程安全）。"""

    def __init__(self, log_dir):
        super().__init__()
        self.log_dir = Path(log_dir)
        self._lock = threading.Lock()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        pid = os.getpid()
        self.path = self.log_dir / f'{stamp}_{pid}.log'
        suffix = 1
        while self.path.exists():
            self.path = self.log_dir / f'{stamp}_{pid}_{suffix}.log'
            suffix += 1
        self._file = open(self.path, 'a', encoding='utf-8')

    def emit(self, record):
        try:
            msg = self.format(record)
            with self._lock:
                # 部分运行环境会提前关闭 logging 句柄，服务仍在运行时应恢复写入。
                if self._file.closed:
                    self._file = open(self.path, 'a', encoding='utf-8')
                self._file.write(msg + '\n')
                self._file.flush()
        except Exception:
            self.handleError(record)

    def current_file(self):
        with self._lock:
            return str(self.path)

    def close(self):
        with self._lock:
            try:
                self._file.close()
            except OSError:
                pass


class SystemLogger:
    """系统日志器：stderr + 日期文件 + 内存回放缓冲"""

    def __init__(self, name='pattern', log_dir=LOG_DIR):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if self.logger.handlers:
            return  # 已初始化（模块重载保护）

        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        console = logging.StreamHandler(stream=sys.stderr)
        console.setFormatter(formatter)
        self.logger.addHandler(console)

        self.file_handler = _RunFileHandler(log_dir)
        self.file_handler.setFormatter(formatter)
        self.logger.addHandler(self.file_handler)

        self.memory_handler = _MemoryBufferHandler(_MEMORY_BUFFER_SIZE)
        self.memory_handler.setFormatter(formatter)
        self.logger.addHandler(self.memory_handler)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def audit(self, message):
        """后台管理操作审计日志"""
        self.logger.info(f'[审计] {message}')

    def replay(self, since_seq=0):
        """回放内存缓冲中的日志（seq 之后的条目）"""
        return self.memory_handler.replay(since_seq)

    def current_file(self):
        return self.file_handler.current_file()

    def shutdown(self):
        for handler in list(self.logger.handlers):
            try:
                handler.close()
            except Exception:
                pass
            self.logger.removeHandler(handler)


_logger = None


def get_logger():
    """获取全局日志器单例"""
    global _logger
    if _logger is None:
        _logger = SystemLogger()
    return _logger
