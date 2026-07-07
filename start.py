#!/usr/bin/env python3
"""
斑图生成器 — 一键启动脚本
=======================
同时启动主站 (:8000) 和后台管理 (:8010)。

用法:
    python start.py                    # 本机访问
    python start.py --host 0.0.0.0     # 局域网访问
    python start.py --no-browser       # 不自动打开浏览器
"""
import argparse
import threading
import asyncio
import webbrowser
import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import uvicorn


def run_server(app_path, host, port, log_level="info"):
    """在线程中运行 uvicorn"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    uvicorn.run(app_path, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="斑图生成器 Web 服务")
    parser.add_argument("--host", default="127.0.0.1",
                        help="监听地址 (默认 127.0.0.1，局域网用 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000,
                        help="主站端口 (默认 8000)")
    parser.add_argument("--admin-port", type=int, default=8010,
                        help="后台管理端口 (默认 8010)")
    parser.add_argument("--no-browser", action="store_true",
                        help="不自动打开浏览器")
    args = parser.parse_args()

    print("=" * 50)
    print("  斑图生成器 v1.3.0")
    print(f"  主站:     http://{args.host}:{args.port}")
    print(f"  后台管理: http://{args.host}:{args.admin_port}")
    print("=" * 50)

    # 启动后台管理（独立线程）
    t = threading.Thread(
        target=run_server,
        args=("server.admin_app:admin_app", args.host, args.admin_port),
        daemon=True,
    )
    t.start()

    # 自动打开浏览器
    if not args.no_browser and args.host in ("127.0.0.1", "localhost"):
        threading.Timer(1.5, lambda: webbrowser.open(
            f"http://{args.host}:{args.port}")).start()

    # 主站在主线程运行
    run_server("server.main:app", args.host, args.port)
