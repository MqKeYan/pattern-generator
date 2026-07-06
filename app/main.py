#!/usr/bin/env python3
"""
斑图生成器 — 应用程序入口
==========================
基于反应-扩散方程的捕食者-猎物斑图生成与可视化工具。

用法:
    python app/main.py
    python -m app.main
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
