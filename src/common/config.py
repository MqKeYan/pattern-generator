"""软件配置模块 - 统管路径、版本号与运行时设置

1. software_root()：开发/packaging 运行路径解析；
2. VERSION：软件版本号；
3. 设置管理：保存启动脚本与 Web 界面共同使用的配置。

配置文件位于 config/settings.json（运行时自动创建）。
迁移链：%LOCALAPPDATA%\\PatternGenerator\\settings.json → 软件根目录 settings.json → config/settings.json。
"""

import json
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from common.persistence import atomic_write_json, backup_corrupt_file
from common.notification_channels import (
    CHANNEL_DEFAULTS,
    merge_channel_targets,
    public_channel_targets,
    public_channel_settings,
    public_pushplus_targets,
    sanitize_channel_settings,
    sanitize_channel_targets,
    sanitize_pushplus_targets,
)


def software_root():
    """软件根目录：打包后为 exe 所在目录，开发时为项目根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    # 本文件位于 src/common/，上两级为项目根目录
    return Path(__file__).resolve().parents[2]


# 版本信息
VERSION = "2.0.0"


DEFAULT_SETTINGS = {
    'port': 5000,
    'admin_port': 5001,
    'monitor_default_view': 'full',
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
        'cpu_percent_threshold': 95,
        'memory_percent_threshold': 90,
        'swap_percent_threshold': 80,
        'disk_used_percent_threshold': 90,
        'gpu_memory_percent_threshold': 90,
        'gpu_power_percent_threshold': 90,
        'cpu_power_percent_threshold': 90,
        'pushplus_enabled': False,
        'pushplus_token': '',
        'pushplus_targets': [],
        'extra_channels': deepcopy(CHANNEL_DEFAULTS),
        'extra_channel_targets': {name: [] for name in CHANNEL_DEFAULTS},
        'alert_events': [
            'queue_backlog', 'gpu_overheat', 'gpu_memory_pressure',
            'memory_pressure', 'disk_space_low', 'client_kicked',
        ],
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
_MONITOR_VIEW_MODES = ('full', 'compact')
_SETTINGS_SECTION_FIELDS = {
    'startup': ('port', 'admin_port', 'auto_open_browser', 'auto_open_admin_browser'),
    'monitor': ('monitor_default_view',),
    'task': (
        'max_compute_concurrency', 'gpu_memory_reserve_mb', 'task_timeout_seconds',
        'task_retry_count', 'request_rate_limit', 'request_rate_window_seconds',
        'task_result_ttl_minutes', 'max_cache_mb',
    ),
}

# notifications 内允许出现的字段及其类型校验
_NOTIFICATION_TYPES = {
    'system_toast': bool,
    'system_sound': bool,
    'queue_backlog_threshold': int,
    'gpu_temp_threshold': int,
    'cpu_percent_threshold': int,
    'memory_percent_threshold': int,
    'swap_percent_threshold': int,
    'disk_used_percent_threshold': int,
    'gpu_memory_percent_threshold': int,
    'gpu_power_percent_threshold': int,
    'cpu_power_percent_threshold': int,
    'pushplus_enabled': bool,
    'pushplus_token': str,
    'pushplus_targets': list,
    'alert_events': list,
    'extra_channels': dict,
    'extra_channel_targets': dict,
}

_NOTIFICATION_INT_RANGES = {
    'queue_backlog_threshold': (0, 100000),
    'gpu_temp_threshold': (0, 150),
    'cpu_percent_threshold': (1, 100),
    'memory_percent_threshold': (1, 100),
    'swap_percent_threshold': (1, 100),
    'disk_used_percent_threshold': (1, 100),
    'gpu_memory_percent_threshold': (1, 100),
    'gpu_power_percent_threshold': (1, 100),
    'cpu_power_percent_threshold': (1, 100),
}


def _config_dir():
    return software_root() / 'config'


def _settings_path():
    return _config_dir() / 'settings.json'


def _root_legacy_path():
    """旧版根目录设置文件路径"""
    return software_root() / 'settings.json'


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


def public_settings(settings):
    """生成可返回给后台前端的设置副本，隐藏通知凭据。"""
    public = dict(settings)
    notifications = dict(public.get('notifications') or {})
    notifications['pushplus_token_configured'] = bool(notifications.get('pushplus_token'))
    notifications.pop('pushplus_token', None)
    notifications['pushplus_targets'] = public_pushplus_targets(notifications.get('pushplus_targets'))
    notifications['extra_channels'] = public_channel_settings(notifications.get('extra_channels'))
    notifications['extra_channel_targets'] = public_channel_targets(notifications.get('extra_channel_targets'))
    public['notifications'] = notifications
    return public


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
    if key == 'monitor_default_view':
        if value not in _MONITOR_VIEW_MODES:
            raise ValueError('monitor_default_view 必须是 full 或 compact')
        return value
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
    has_pushplus_targets = 'pushplus_targets' in data
    has_channel_targets = 'extra_channel_targets' in data
    has_legacy_channels = 'extra_channels' in data
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
        elif key == 'extra_channels':
            merged[key] = sanitize_channel_settings(value)
        elif key == 'pushplus_targets':
            merged[key] = sanitize_pushplus_targets(value)
        elif key == 'extra_channel_targets':
            merged[key] = sanitize_channel_targets(value)
        elif isinstance(value, expected):
            if key == 'alert_events' and any(not isinstance(item, str) for item in value):
                continue
            merged[key] = value
    if not has_pushplus_targets and merged['pushplus_token']:
        merged['pushplus_targets'] = [{
            'id': 'legacy-default',
            'name': '默认 PushPlus',
            'token': merged['pushplus_token'],
            'enabled': merged['pushplus_enabled'],
        }]
    if not has_channel_targets and has_legacy_channels:
        merged['extra_channel_targets'] = sanitize_channel_targets(merged['extra_channels'])
    return merged


def _merge_pushplus_targets(existing, incoming):
    """后台页面不会回传旧 Token，按目标 ID 合并保留未修改凭据。"""
    previous = {item['id']: item for item in sanitize_pushplus_targets(existing)}
    merged = []
    if not isinstance(incoming, list):
        return merged
    for item in incoming:
        if not isinstance(item, dict):
            continue
        candidate = dict(item)
        target_id = str(candidate.get('id', '')).strip()
        if not str(candidate.get('token', '')).strip() and target_id in previous:
            candidate['token'] = previous[target_id]['token']
        merged.append(candidate)
    return sanitize_pushplus_targets(merged)


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
                elif key == 'monitor_default_view':
                    if value in _MONITOR_VIEW_MODES:
                        settings[key] = value
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
                if isinstance(value.get('extra_channels'), dict):
                    channels = dict(merged.get('extra_channels') or {})
                    for name, channel in value['extra_channels'].items():
                        previous = dict(channels.get(name) or {})
                        if isinstance(channel, dict):
                            previous.update(channel)
                        channels[name] = previous
                    value = dict(value)
                    value['extra_channels'] = channels
                if isinstance(value.get('pushplus_targets'), list):
                    value = dict(value)
                    value['pushplus_targets'] = _merge_pushplus_targets(
                        merged.get('pushplus_targets'),
                        value['pushplus_targets'],
                    )
                if isinstance(value.get('extra_channel_targets'), dict):
                    value = dict(value)
                    value['extra_channel_targets'] = merge_channel_targets(
                        merged.get('extra_channel_targets'),
                        value['extra_channel_targets'],
                    )
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


def reset_settings_section(section):
    """只恢复系统设置页面中指定卡片的可见字段。"""
    fields = _SETTINGS_SECTION_FIELDS.get(section)
    if fields is None:
        raise ValueError('设置卡片无效')
    settings = load_settings()
    for key in fields:
        settings[key] = deepcopy(DEFAULT_SETTINGS[key])
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, settings)
    return settings
