# -*- mode: python ; coding: utf-8 -*-
"""
Pattern-Generator — PyInstaller 打包规格文件
====================================
优化：onedir 模式启动更快，无临时解压开销。
白名单控制依赖，排除无用模块缩小体积。

用法:
    pyinstaller Pattern-Generator.spec       # 打包
    pyinstaller --clean Pattern-Generator.spec # 清理重打包
"""

import os
import sys
import PyInstaller.config

# 输出路径：build 放入 dist 内，方便管理
PyInstaller.config.CONF['workpath'] = 'dist/_build'
os.makedirs('dist/_build', exist_ok=True)

# 使用相对路径避免中文目录编码问题

# ── 白名单：只打包这些顶层库 ─────────────────────────────
ALLOW_TOP = {
    "fastapi", "uvicorn", "starlette", "anyio", "sniffio",
    "h11", "httptools", "websockets", "uvloop", "watchfiles",
    "aiofiles", "httpcore", "httpx",
    "pydantic", "pydantic_core", "annotated_types",
    "typing_extensions", "typing_inspection", "exceptiongroup",
    "torch", "numpy", "psutil", "multiprocessing",
}

# ── uvicorn 动态加载 ─────────────────────────────────────
UVICORN_HIDDEN = [
    "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on", "uvicorn.logging",
    "uvicorn.middleware.proxy_headers",
]

# ── 其他隐藏导入 ─────────────────────────────────────────
HIDDEN_IMPORTS = [
    *UVICORN_HIDDEN,
    "fastapi.staticfiles", "fastapi.middleware.cors",
    "fastapi.middleware.gzip", "starlette.responses",
    "starlette.routing", "starlette.websockets",
    "anyio._backends._asyncio",
    "torch._C", "torch._VF",
    "multiprocessing.process", "multiprocessing.connection",
]

# ── Torch 共享库保护（防止被误排除） ─────────────────────
torch_binaries = []
try:
    import torch
    torch_lib = os.path.join(os.path.dirname(torch.__file__), 'lib')
    for f in os.listdir(torch_lib):
        fp = os.path.join(torch_lib, f)
        if os.path.isfile(fp) and f.endswith(('.dll', '.dylib', '.so')):
            torch_binaries.append((fp, 'torch/lib'))
except (ImportError, FileNotFoundError):
    pass

# ── 数据文件 ─────────────────────────────────────────────
datas = [
    ('app/web', 'app/web'),
]

a = Analysis(
    ['start.py'],
    pathex=[],
    binaries=torch_binaries,
    datas=datas,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests'],  # 测试仅开发用，不打包
    noarchive=False,
    optimize=0,
)

# ── 二次过滤 ─────────────────────────────────────────────
# 保留：标准库 + 项目代码 + 白名单第三方库，其余剔除
STDLIB_NAMES = set(sys.stdlib_module_names if hasattr(sys, 'stdlib_module_names') else [])
STDLIB_NAMES.update(sys.builtin_module_names)
PROJECT_TOPS = {'app', 'start'}

filtered_pure = []
for name, path, code in a.pure:
    top = name.split('.')[0]
    if top in ALLOW_TOP or top in PROJECT_TOPS or top in STDLIB_NAMES or name in HIDDEN_IMPORTS:
        filtered_pure.append((name, path, code))

a.pure = filtered_pure

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Pattern-Generator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # 禁用 UPX，启动更快
    console=False,    # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Pattern-Generator",
)
