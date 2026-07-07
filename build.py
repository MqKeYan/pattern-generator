#!/usr/bin/env python3
"""
斑图生成器 — 打包构建脚本
========================
将 Web 服务打包为单个 .exe 文件，白名单控制依赖，排除无用库。

用法:
    python build.py              # 打包为单文件 .exe
    python build.py --clean      # 清理后重新打包
    python build.py --console    # 保留控制台窗口（调试用）
"""

import subprocess
import sys
import os
import shutil

# 项目根目录
ROOT = os.path.dirname(os.path.abspath(__file__))

# ── 依赖白名单 ──────────────────────────────────────────────
# 只有白名单中的库会打包进去，其余全部排除。

ALLOW_MODULES = [
    # Web 框架
    "fastapi",
    "uvicorn",
    "starlette",
    "anyio",
    "sniffio",
    "h11",
    "httpcore",
    "httpx",
    "websockets",
    "httptools",
    "uvloop",
    "watchfiles",
    "aiofiles",
    "python_multipart",
    "pydantic",
    "pydantic_core",
    "annotated_types",
    "typing_extensions",
    "typing_inspection",
    "exceptiongroup",

    # 计算引擎
    "torch",
    "numpy",

    # 系统监控
    "psutil",

    # 标准库补充（PyInstaller 有时遗漏）
    "asyncio",
    "concurrent.futures",
    "multiprocessing",
    "json",
    "uuid",
    "argparse",
    "logging",
]

# ── 强制排除 ────────────────────────────────────────────────
# 这些库即使被检测到也排除，缩小体积。

BLOCK_MODULES = [
    "tkinter",
    "turtle",
    "matplotlib",
    "PIL",
    "Pillow",
    "scipy",
    "pandas",
    "jupyter",
    "IPython",
    "notebook",
    "nbformat",
    "nbconvert",
    "tornado",
    "zmq",
    "sqlalchemy",
    "alembic",
    "flask",
    "django",
    "jinja2",
    "click",        # uvicorn 标准安装带 click，但实际不需要
    "rich",
    "prompt_toolkit",
    "curses",
    "readline",
    "pytest",
    "setuptools",
    "pip",
    "wheel",
    "distutils",
    "email",
    "html",
    "http.server",
    "xmlrpc",
    "pdb",
    "doctest",
    "unittest",
    "test",
    "tests",
    "antigravity",
    "turtle",
    "ensurepip",
    "idlelib",
    "zoneinfo",
]


def build():
    """执行 PyInstaller 打包"""
    # ── 输出目录清理 ─────────────────────────────────────
    for d in ["build", "dist"]:
        path = os.path.join(ROOT, d)
        if os.path.isdir(path) and "--clean" in sys.argv:
            shutil.rmtree(path)
            print(f"[清理] {d}/")

    # ── PyInstaller 参数 ─────────────────────────────────
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "斑图生成器",
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", os.path.join(ROOT, "build"),
        "--add-data", f"{os.path.join(ROOT, 'web')};web",
        # 入口文件
        os.path.join(ROOT, "start.py"),
    ]

    # 控制台窗口
    if "--console" not in sys.argv:
        cmd.insert(4, "--noconsole")

    # 白名单模块（强制导入，防止遗漏）
    for name in ALLOW_MODULES:
        cmd.extend(["--hidden-import", name])

    # 黑名单模块（强制排除，减小体积）
    for name in BLOCK_MODULES:
        cmd.extend(["--exclude-module", name])

    # uvicorn 子模块（动态加载，必须显式声明）
    uvicorn_imports = [
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan.on",
        "uvicorn.logging",
        "uvicorn.middleware.proxy_headers",
        "uvicorn.middleware.wsgi",
    ]
    for name in uvicorn_imports:
        cmd.extend(["--hidden-import", name])

    # fastapi/starlette 子模块
    fastapi_imports = [
        "fastapi.middleware.cors",
        "fastapi.middleware.gzip",
        "fastapi.staticfiles",
        "starlette.responses",
        "starlette.routing",
        "starlette.middleware",
        "starlette.websockets",
        "anyio._backends._asyncio",
    ]
    for name in fastapi_imports:
        cmd.extend(["--hidden-import", name])

    # torch 子模块
    torch_imports = [
        "torch._C",
        "torch._VF",
        "torch.distributed",
    ]
    for name in torch_imports:
        cmd.extend(["--hidden-import", name])

    print("[打包] 正在打包...")
    print(f"[命令] {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("\n[失败] 打包出错，请检查上方日志")
        sys.exit(1)

    # ── 输出结果 ──────────────────────────────────────────
    exe_path = os.path.join(ROOT, "dist", "斑图生成器.exe")
    size_mb = os.path.getsize(exe_path) / 1024 / 1024
    print(f"\n{'=' * 50}")
    print(f"  打包完成")
    print(f"  文件: {exe_path}")
    print(f"  大小: {size_mb:.1f} MB")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    # 检查 PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[安装] 正在安装 PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    build()
