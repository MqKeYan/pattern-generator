# -*- mode: python ; coding: utf-8 -*-
"""
斑图生成器 — PyInstaller 打包规格文件
====================================
优化：onedir 模式启动更快，无临时解压开销。
白名单控制依赖，排除无用模块缩小体积。

用法:
    pyinstaller 斑图生成器.spec       # 打包
    pyinstaller --clean 斑图生成器.spec # 清理重打包
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent

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
torch_lib = None
try:
    import torch
    torch_lib = Path(torch.__file__).parent / "lib"
except ImportError:
    pass

torch_binaries = []
if torch_lib and torch_lib.exists():
    torch_binaries = [
        (str(f), "torch/lib")
        for f in torch_lib.glob("*.dll") if f.name != "caffe2_nvrtc.dll"
    ] + [
        (str(f), "torch/lib")
        for f in torch_lib.glob("*.dylib")
    ] + [
        (str(f), "torch/lib")
        for f in torch_lib.glob("*.so*")
    ]

# ── 数据文件 ─────────────────────────────────────────────
datas = [
    (str(ROOT / "web"), "web"),
]

a = Analysis(
    str(ROOT / "start.py"),
    pathex=[str(ROOT)],
    binaries=torch_binaries,
    datas=datas,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# ── 二次过滤 ─────────────────────────────────────────────
# 只保留白名单内的模块，其余剔除
filtered_pure = []
for name, path, code in a.pure:
    top = name.split(".")[0]
    if top in ALLOW_TOP or name in HIDDEN_IMPORTS:
        filtered_pure.append((name, path, code))

a.pure = filtered_pure

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="斑图生成器",
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
    name="斑图生成器",
)
