"""软件运行时路径，统一兼容开发目录和 PyInstaller 启动目录。"""

import sys
from pathlib import Path


def software_root():
    """开发时返回项目根目录，打包时返回 exe 所在目录。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]
