"""软件共享设置 - 保存启动脚本与Web界面共同使用的配置

配置文件位于 config/settings.json（运行时自动创建）。
迁移链：%LOCALAPPDATA%\\PatternGenerator\\settings.json → 软件根目录 settings.json → config/settings.json。
"""

import json
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from persistence import atomic_write_json, backup_corrupt_file


DEFAULT_SETTINGS = {
    'port': 5000,
    'admin_port': 5001,
    'auto_open_browser': True,
    'auto_open_admin_browser': True,
    'auto_open_browser_configured': False,
    'max_compute_concurrency': 1,
    'task_timeout_seconds': 300,
    'task_retry_count': 1,
    'request_rate_limit': 10,
    'request_rate_window_seconds': 60,
    'task_result_ttl_minutes': 30,
    'max_cache_mb': 1024,
    'max_cache_files': 2048,
    'max_cache_file_mb': 256,
    'max_queue_tasks': 100,
    'max_history_tasks': 500,
    'max_dead_tasks': 100,
    'max_clients': 1024,
    'max_presence_sockets': 2048,
    'max_presence_sockets_per_client': 4,
    'max_request_body_bytes': 2 * 1024 * 1024,
    'allowed_hosts': [],
    'metrics_window_seconds': 180,
    'notifications': {
        'system_toast': True,
        'system_sound': True,
        'queue_backlog_threshold': 10,
        'gpu_temp_threshold': 85,
        'pushplus_enabled': False,
        'pushplus_token': '',
        'pushplus_topic': '',
        'alert_events': ['task_failed', 'queue_backlog', 'gpu_overheat'],
    },
    'gpu_memory_reserve_mb': 512,
}

# 顶层整型字段的合法范围：(最小值, 最大值)
_INT_RANGES = {
    'port': (1024, 65535),
    'admin_port': (1024, 65535),
    'max_compute_concurrency': (1, 16),
    'task_timeout_seconds': (10, 86400),
    'task_retry_count': (0, 10),
    'request_rate_limit': (1, 100000),
    'request_rate_window_seconds': (1, 3600),
    'task_result_ttl_minutes': (1, 1440),
    'max_cache_mb': (64, 65536),
    'metrics_window_seconds': (30, 3600),
    'gpu_memory_reserve_mb': (0, 8192),
    'max_queue_tasks': (1, 10000),
    'max_history_tasks': (1, 10000),
    'max_dead_tasks': (1, 10000),
    'max_clients': (1, 100000),
    'max_presence_sockets': (1, 100000),
    'max_presence_sockets_per_client': (1, 64),
    'max_request_body_bytes': (1024, 16 * 1024 * 1024),
    'max_cache_files': (1, 100000),
    'max_cache_file_mb': (1, 4096),
}

_BOOL_FIELDS = ('auto_open_browser', 'auto_open_admin_browser', 'auto_open_browser_configured')

# notifications 内允许出现的字段及其类型校验
_NOTIFICATION_TYPES = {
    'system_toast': bool,
    'system_sound': bool,
    'queue_backlog_threshold': int,
    'gpu_temp_threshold': int,
    'pushplus_enabled': bool,
    'pushplus_token': str,
    'pushplus_topic': str,
    'alert_events': list,
}

_NOTIFICATION_INT_RANGES = {
    'queue_backlog_threshold': (0, 100000),
    'gpu_temp_threshold': (0, 150),
}


def public_settings(settings):
    """生成可返回给后台前端的设置副本，隐藏通知凭据。"""
    public = dict(settings)
    notifications = dict(public.get('notifications') or {})
    notifications['pushplus_token_configured'] = bool(notifications.get('pushplus_token'))
    notifications.pop('pushplus_token', None)
    public['notifications'] = notifications
    return public


def _software_root():
    """软件根目录：打包后为 exe 所在目录，开发时为项目根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _config_dir():
    return _software_root() / 'config'


def _settings_path():
    return _config_dir() / 'settings.json'


def _root_legacy_path():
    """旧版根目录设置文件路径"""
    return _software_root() / 'settings.json'


def _localappdata_legacy_path():
    """最旧版用户目录设置文件路径"""
    base_dir = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or Path.home()
    return Path(base_dir) / 'PatternGenerator' / 'settings.json'


def _migrate_legacy_settings():
    """逐级迁移：用户目录 → 软件根目录 → config/ 目录"""
    config_path = _settings_path()
    if config_path.exists():
        return
    try:
        _config_dir().mkdir(parents=True, exist_ok=True)
        root_legacy = _root_legacy_path()
        if root_legacy.exists():
            shutil.move(str(root_legacy), str(config_path))
            return
        localappdata_legacy = _localappdata_legacy_path()
        if localappdata_legacy.exists():
            shutil.move(str(localappdata_legacy), str(config_path))
    except OSError:
        pass


def _validate_field(key, value):
    """校验单个字段，非法时抛出 ValueError"""
    if key in _INT_RANGES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{key} 必须是整数')
        lo, hi = _INT_RANGES[key]
        if not lo <= value <= hi:
            raise ValueError(f'{key} 超出范围 {lo}-{hi}')
        return value
    if key in _BOOL_FIELDS:
        if not isinstance(value, bool):
            raise ValueError(f'{key} 必须是布尔值')
        return value
    if key == 'allowed_hosts':
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError('allowed_hosts 必须是字符串数组')
        return [item.strip().lower() for item in value if item.strip()][:64]
    if key == 'notifications':
        if not isinstance(value, dict):
            raise ValueError('notifications 必须是对象')
        return value
    raise KeyError(key)


def _sanitize_notifications(data):
    """校验并合并 notifications 子字段，未知子字段保留"""
    merged = deepcopy(DEFAULT_SETTINGS['notifications'])
    if not isinstance(data, dict):
        return merged
    for key, value in data.items():
        expected = _NOTIFICATION_TYPES.get(key)
        if expected is None:
            merged[key] = value  # 未知子字段保留
            continue
        if expected is int:
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            lo, hi = _NOTIFICATION_INT_RANGES.get(key, (0, 100000))
            if not lo <= value <= hi:
                continue
            merged[key] = value
        elif isinstance(value, expected):
            if key == 'alert_events' and any(not isinstance(item, str) for item in value):
                continue
            merged[key] = value
    return merged


def load_settings():
    """读取设置：默认值与文件内容深度合并，未知字段原样保留"""
    settings = deepcopy(DEFAULT_SETTINGS)
    _migrate_legacy_settings()
    try:
        data = json.loads(_settings_path().read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return settings
        for key, value in data.items():
            try:
                if key == 'notifications':
                    settings[key] = _sanitize_notifications(value)
                elif key in _INT_RANGES:
                    lo, hi = _INT_RANGES[key]
                    if isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi:
                        settings[key] = value
                elif key in _BOOL_FIELDS:
                    if isinstance(value, bool):
                        settings[key] = value
                elif key == 'allowed_hosts':
                    if isinstance(value, list) and all(isinstance(item, str) for item in value):
                        settings[key] = [item.strip().lower() for item in value if item.strip()][:64]
                else:
                    settings[key] = value  # 未知字段保留，避免保存时丢失
            except (ValueError, TypeError):
                continue
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        backup_corrupt_file(_settings_path())
    return settings


def update_settings(**updates):
    """更新设置并持久化，未知/未提及字段保持不变"""
    settings = load_settings()
    for key, value in updates.items():
        if value is None:
            continue
        if key == 'notifications':
            merged = dict(settings.get('notifications') or {})
            if isinstance(value, dict):
                merged.update(value)
            settings[key] = _sanitize_notifications(merged)
            continue
        try:
            settings[key] = _validate_field(key, value)
        except KeyError:
            continue  # 未知字段丢弃，防止污染配置文件
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, settings)
    return settings


def reset_settings():
    """恢复默认设置并持久化"""
    settings = deepcopy(DEFAULT_SETTINGS)
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, settings)
    return settings
