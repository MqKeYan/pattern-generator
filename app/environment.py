"""
环境配置模块
============
管理操作系统环境变量和 matplotlib 字体配置。
必须在导入其他模块之前完成设置。
"""

import os
import matplotlib
import matplotlib.font_manager as fm


def setup_environment():
    """设置运行时环境变量

    - KMP_DUPLICATE_LIB_OK: 解决 Intel MKL/OpenMP 库冲突
    - MPLBACKEND: 指定 matplotlib 使用 TkAgg 后端
    """
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
    os.environ['MPLBACKEND'] = 'TkAgg'


def setup_chinese_fonts():
    """配置 matplotlib 中文字体支持

    自动检测系统中可用的中文字体并应用。

    返回:
        str | None: 成功时返回字体名称，失败返回 None
    """
    candidates = [
        'Microsoft YaHei', 'SimHei', 'SimSun', 'NSimSun',
        'FangSong', 'KaiTi', 'STXihei', 'STKaiti', 'STSong',
    ]
    for name in candidates:
        if any(name in f.name for f in fm.fontManager.ttflist):
            matplotlib.rcParams['font.sans-serif'] = [name]
            matplotlib.rcParams['axes.unicode_minus'] = False
            return name
    return None


def get_project_root():
    """返回项目根目录的绝对路径"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
