# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — 斑图形成可视化系统
使用方式：
    pyinstaller pattern-generator.spec
白名单策略：扫描环境所有第三方模块，排除不在白名单中的，
            PyTorch 不在白名单中，由用户自行安装。
"""

from PyInstaller.utils.hooks import collect_submodules
import os
import sys
import pkgutil

# ============================================================
# 项目路径
# ============================================================
PROJECT_ROOT = os.getcwd()

# ============================================================
# 白名单：项目实际依赖的 Python 模块
# 注意：torch相关模块不在白名单中，由用户自行安装
# ============================================================
_MODULE_WHITELIST = [
    # 计算引擎
    'numpy',
    # Web 框架
    'flask', 'jinja2', 'markupsafe', 'werkzeug', 'blinker',
    'click', 'itsdangerous',
    # WSGI 服务器
    'waitress',
    # 系统监控
    'psutil',
]

# ============================================================
# 子模块收集（解决动态导入问题）
# ============================================================
numpy_hidden = collect_submodules('numpy')
flask_hidden = collect_submodules('flask')
jinja2_hidden = collect_submodules('jinja2')

# PyTorch依赖的标准库模块
stdlib_hidden = [
    'pickletools',
]

# 排除torch相关模块（由用户自行安装）
excludes_list = [
    'torch', 'torchvision', 'torchaudio',
    'torch.*', 'torchvision.*', 'torchaudio.*',
    'nvidia', 'cuda', 'cudnn', 'triton'
]

# ============================================================
# 自动构建 excludes：排除所有非白名单的第三方模块
# ============================================================
def _get_all_top_level_modules():
    """获取当前环境中所有可导入的顶级模块名称"""
    modules = set()
    modules.update(sys.builtin_module_names)
    for pkg in pkgutil.iter_modules():
        modules.add(pkg.name)
    if hasattr(sys, 'stdlib_module_names'):
        modules.update(sys.stdlib_module_names)
    return modules

def _build_whitelist_excludes(whitelist, all_modules):
    """构建排除列表 = 环境第三方模块 - 白名单模块，标准库和内置模块永远不排除"""
    stdlib = set(sys.builtin_module_names)
    if hasattr(sys, 'stdlib_module_names'):
        stdlib.update(sys.stdlib_module_names)

    # 保护列表：白名单模块 + 标准库模块（避免误排除）
    protected = set(whitelist)

    third_party = all_modules - stdlib
    to_exclude = sorted(third_party - protected)
    return to_exclude

_whitelist_excludes = _build_whitelist_excludes(
    _MODULE_WHITELIST,
    _get_all_top_level_modules(),
)

print(f"[spec] 白名单模块: {len(_MODULE_WHITELIST)} 个")
print(f"[spec] 将排除: {len(_whitelist_excludes)} 个无关第三方模块")

# ============================================================
# 数据文件
# ============================================================
ADDED_DATAS = [
    (os.path.join(PROJECT_ROOT, 'src', 'web', 'templates'), 'src/web/templates'),
    (os.path.join(PROJECT_ROOT, 'src', 'web', 'static'), 'src/web/static'),
]

# 应用名称（小写）
APP_NAME = 'pattern-generator'

block_cipher = None

# 合并排除列表（白名单排除 + 明确排除torch）
final_excludes = list(set(_whitelist_excludes + excludes_list))

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'run.py')],
    pathex=[PROJECT_ROOT, os.path.join(PROJECT_ROOT, 'src')],
    binaries=[],
    datas=ADDED_DATAS,
    hiddenimports=numpy_hidden + flask_hidden + jinja2_hidden + stdlib_hidden,
    hookspath=[],
    hooksconfig={},
    excludes=final_excludes,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_ROOT, 'src', 'web', 'static', 'favicon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
