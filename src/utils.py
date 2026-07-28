"""工具函数 - 环境设置和辅助功能"""

import os
import sys

def setup_environment():
    """设置环境变量，解决OpenMP冲突"""
    # 解决OpenMP库重复初始化问题
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

    # 防止matplotlib使用agg后端（某些系统上会导致问题）
    os.environ['MPLBACKEND'] = 'TkAgg'