"""访问控制 - 黑白名单、局域网限制、IP + client_id 双维度频率限制

- 白名单优先，黑名单次之，默认仅允许局域网私有 IP 段。
- client_id 由浏览器端自行生成，服务端不假设其真实性，封禁与限流以 IP 维度兜底。
- 仅信任 request.remote_addr 直连地址，不解析转发头。
"""

import ipaddress
import json
import threading
import time
from collections import deque
from pathlib import Path
from common.persistence import atomic_write_json, backup_corrupt_file
from common.config import software_root

SOFTWARE_ROOT = software_root()
CONFIG_DIR = SOFTWARE_ROOT / 'config'

# 主服务默认允许的私有网段
_ALLOWED_NETWORKS = [
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
]

_DENIED_BUFFER_SIZE = 500
_RATE_KEY_LIMIT = 4096


def _is_private_ip(ip):
    """判断是否属于允许的局域网私有网段"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _ALLOWED_NETWORKS)


def _validate_ip_entry(entry):
    """校验名单条目：单个 IP 或 CIDR 段"""
    _as_network(entry)


def _as_network(entry):
    """将单个 IP 或 CIDR 统一转换为可匹配网段。"""
    value = str(entry).strip()
    if '/' in value:
        return ipaddress.ip_network(value, strict=False)
    address = ipaddress.ip_address(value)
    return ipaddress.ip_network(f'{address}/{address.max_prefixlen}', strict=False)


def _matches_ip(entries, ip):
    """判断请求 IP 是否命中名单中的单个地址或 CIDR 网段。"""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in entries:
        try:
            if address in _as_network(entry):
                return True
        except ValueError:
            continue
    return False


class AccessControl:
    """黑白名单与频率限制"""

    def __init__(self, logger=None):
        self.log = logger
        self._lock = threading.RLock()
        self._blacklist = {'ips': [], 'client_ids': []}
        self._whitelist = {'ips': [], 'client_ids': []}
        self._rate = {}  # key -> deque[timestamp]
        self._denied = deque(maxlen=_DENIED_BUFFER_SIZE)
        self._load()

    # ---------- 名单持久化 ----------

    def _blacklist_path(self):
        return CONFIG_DIR / 'blacklist.json'

    def _whitelist_path(self):
        return CONFIG_DIR / 'whitelist.json'

    def _load(self):
        for attr, path in (('_blacklist', self._blacklist_path()), ('_whitelist', self._whitelist_path())):
            data = {'ips': [], 'client_ids': []}
            try:
                loaded = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(loaded, dict):
                    data['ips'] = [str(i) for i in loaded.get('ips', []) if isinstance(i, str)]
                    data['client_ids'] = [str(c) for c in loaded.get('client_ids', []) if isinstance(c, str)]
            except (OSError, ValueError, json.JSONDecodeError):
                backup_corrupt_file(path)
                pass
            setattr(self, attr, data)

    def _save(self, attr, path):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(path, getattr(self, attr))
        except OSError as e:
            if self.log:
                self.log.error(f'名单写入失败 {path.name}: {e}')

    # ---------- 判定 ----------

    def is_allowed(self, ip, client_id):
        """判定是否允许访问，返回 (是否允许, 原因)"""
        with self._lock:
            if client_id and client_id in self._whitelist['client_ids']:
                return True, 'whitelist'
            if _matches_ip(self._whitelist['ips'], ip):
                return True, 'whitelist'
            if client_id and client_id in self._blacklist['client_ids']:
                return False, 'blacklist_client'
            if _matches_ip(self._blacklist['ips'], ip):
                return False, 'blacklist_ip'
        if not _is_private_ip(ip):
            return False, 'non_private_ip'
        return True, 'ok'

    def check_rate_limit(self, ip, client_id, limit, window_seconds):
        """双维度滑动窗口限流，任一超限即拒绝；仅对任务提交接口调用"""
        now = time.time()
        with self._lock:
            stale_keys = [key for key, window in self._rate.items()
                          if not window or now - window[-1] > window_seconds]
            for key in stale_keys:
                self._rate.pop(key, None)
            keys = [key for key in (f'ip:{ip}', f'cid:{client_id}') if key.split(':', 1)[1]]
            windows = []
            for key in keys:
                window = self._rate.setdefault(key, deque())
                while window and now - window[0] > window_seconds:
                    window.popleft()
                if len(window) >= limit:
                    return False
                windows.append(window)
            for window in windows:
                window.append(now)
            if len(self._rate) > _RATE_KEY_LIMIT:
                oldest = sorted(self._rate.items(), key=lambda item: item[1][-1] if item[1] else 0)
                for key, _window in oldest[:len(self._rate) - _RATE_KEY_LIMIT]:
                    self._rate.pop(key, None)
            return True

    # ---------- 被拒绝记录 ----------

    def record_denied(self, ip, client_id, reason):
        with self._lock:
            self._denied.append({
                'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'ip': ip,
                'client_id': client_id or '',
                'reason': reason,
            })

    def denied_events(self):
        with self._lock:
            return list(self._denied)

    # ---------- 名单管理 ----------

    def get_lists(self):
        with self._lock:
            return {
                'blacklist': {k: list(v) for k, v in self._blacklist.items()},
                'whitelist': {k: list(v) for k, v in self._whitelist.items()},
            }

    def _update_list(self, attr, kind, action, entry):
        """action: add / remove；entry 需通过 IP/CIDR 校验（client_id 不校验格式）"""
        if kind == 'ips':
            _validate_ip_entry(entry)
        with self._lock:
            box = getattr(self, attr)
            if action == 'add':
                if entry not in box[kind]:
                    box[kind].append(entry)
            elif entry in box[kind]:
                box[kind].remove(entry)
        self._save(attr, self._blacklist_path() if attr == '_blacklist' else self._whitelist_path())

    def update_blacklist(self, action, kind, entry):
        self._update_list('_blacklist', kind, action, entry)

    def update_whitelist(self, action, kind, entry):
        self._update_list('_whitelist', kind, action, entry)

    def add_blacklist(self, ip=None, client_id=None):
        """踢出场景：IP 与 client_id 同时封禁"""
        if ip:
            self.update_blacklist('add', 'ips', ip)
        if client_id:
            self.update_blacklist('add', 'client_ids', client_id)

    def replace_lists(self, blacklist=None, whitelist=None):
        """配置导入用：整体替换名单并写盘"""
        with self._lock:
            if isinstance(blacklist, dict):
                self._blacklist = {
                    'ips': [str(i) for i in blacklist.get('ips', []) if isinstance(i, str)],
                    'client_ids': [str(c) for c in blacklist.get('client_ids', []) if isinstance(c, str)],
                }
            if isinstance(whitelist, dict):
                self._whitelist = {
                    'ips': [str(i) for i in whitelist.get('ips', []) if isinstance(i, str)],
                    'client_ids': [str(c) for c in whitelist.get('client_ids', []) if isinstance(c, str)],
                }
        self._save('_blacklist', self._blacklist_path())
        self._save('_whitelist', self._whitelist_path())
