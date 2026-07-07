#!/usr/bin/env python3
"""
斑图生成器 — 打包构建脚本
========================
基于 .spec 文件调用 PyInstaller 打包。

用法:
    python build.py              # 打包 (.spec 文件)
    python build.py --clean      # 清理后重新打包
    python build.py --console    # 保留控制台窗口（调试用）
    python build.py --onefile    # 单文件模式（启动较慢）
"""

import subprocess
import sys
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC_FILE = os.path.join(ROOT, "斑图生成器.spec")


def build():
    # ── 安装 PyInstaller ─────────────────────────────────
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[安装] PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # ── 清理 ─────────────────────────────────────────────
    if "--clean" in sys.argv:
        for d in ["build", "dist"]:
            path = os.path.join(ROOT, d)
            if os.path.isdir(path):
                shutil.rmtree(path)
                print(f"[清理] {d}/")

    # ── 打包 ─────────────────────────────────────────────
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        SPEC_FILE,
    ]

    if "--clean" in sys.argv:
        cmd.insert(2, "--clean")

    print(f"[打包] pyinstaller 斑图生成器.spec")
    result = subprocess.run(cmd, cwd=ROOT)

    if result.returncode != 0:
        print("\n[失败] 打包出错")
        sys.exit(1)

    # ── 结果 ─────────────────────────────────────────────
    dist_dir = os.path.join(ROOT, "dist", "斑图生成器")
    exe_path = os.path.join(dist_dir, "斑图生成器.exe")
    if os.path.isfile(exe_path):
        total_mb = sum(
            os.path.getsize(os.path.join(r, f))
            for r, _, fs in os.walk(dist_dir) for f in fs
        ) / 1024 / 1024

        print(f"\n{'=' * 50}")
        print(f"  打包完成 (onedir 模式 — 启动更快)")
        print(f"  目录: {dist_dir}")
        print(f"  体积: {total_mb:.1f} MB")
        print(f"{'=' * 50}")
    else:
        print("\n[失败] .exe 未生成，检查上方日志")
        sys.exit(1)


if __name__ == "__main__":
    build()
