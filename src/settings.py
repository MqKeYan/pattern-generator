"""软件共享设置 - 保存启动脚本与Web界面共同使用的配置"""

import json
import os
import shutil
import sys
from pathlib import Path


DEFAULT_SETTINGS = {
    'port': 5000,
    'auto_open_browser': True,
    'auto_open_browser_configured': False,
}


def _settings_path():
    """获取软件根目录下的设置文件路径"""
    if getattr(sys, 'frozen', False):
        software_root = Path(sys.executable).resolve().parent
    else:
        software_root = Path(__file__).resolve().parents[1]
    return software_root / 'settings.json'


def _legacy_settings_path():
    """获取旧版用户目录设置文件路径"""
    base_dir = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or Path.home()
    return Path(base_dir) / 'PatternGenerator' / 'settings.json'


def _migrate_legacy_settings():
    """首次读取时将旧设置迁移到软件根目录"""
    new_path = _settings_path()
    old_path = _legacy_settings_path()
    if new_path.exists() or not old_path.exists() or new_path == old_path:
        return
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
    except OSError:
        pass


def load_settings():
    """读取设置，文件不存在或内容无效时返回默认值"""
    settings = DEFAULT_SETTINGS.copy()
    _migrate_legacy_settings()
    try:
        data = json.loads(_settings_path().read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('设置内容无效')
        port = data.get('port', settings['port'])
        if isinstance(port, bool) or not 1024 <= int(port) <= 65535:
            raise ValueError('端口范围无效')
        settings['port'] = int(port)
        if isinstance(data.get('auto_open_browser'), bool):
            settings['auto_open_browser'] = data['auto_open_browser']
        if isinstance(data.get('auto_open_browser_configured'), bool):
            settings['auto_open_browser_configured'] = data['auto_open_browser_configured']
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return settings


def update_settings(port=None, auto_open_browser=None, auto_open_browser_configured=None):
    """更新设置并持久化到用户配置文件"""
    settings = load_settings()
    if port is not None:
        if isinstance(port, bool) or not 1024 <= int(port) <= 65535:
            raise ValueError('端口范围必须为1024-65535')
        settings['port'] = int(port)
    if auto_open_browser is not None:
        if not isinstance(auto_open_browser, bool):
            raise ValueError('自动打开浏览器设置无效')
        settings['auto_open_browser'] = auto_open_browser
    if auto_open_browser_configured is not None:
        if not isinstance(auto_open_browser_configured, bool):
            raise ValueError('自动打开浏览器初始化状态无效')
        settings['auto_open_browser_configured'] = auto_open_browser_configured

    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    return settings
