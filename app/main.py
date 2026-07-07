#!/usr/bin/env python3
"""
斑图生成器 — 应用程序入口 (旧版 tkinter，已废弃)
============================================
请使用项目根目录的 start.py 启动 Web 版本：
    python start.py --host 0.0.0.0
    主站:     http://<IP>:8000
    后台管理: http://<IP>:8010

旧版 tkinter 桌面版本保留仅供参考：
    python app/main.py
"""

import os
import sys

# 将项目根目录加入 Python 路径
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 环境变量必须在导入其他模块之前设置
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['MPLBACKEND'] = 'TkAgg'

import tkinter as tk
from app.app_window import PatternVisualizationApp


def main():
    """启动斑图生成器"""
    root = tk.Tk()
    app = PatternVisualizationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
