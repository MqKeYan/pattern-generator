"""
后台管理 FastAPI 应用
==================
端口 :8010，提供：
- 静态文件服务 (admin.html)
- Worker 池配置 API (/api/pool/*)
- 系统监控 API (/api/system/*)
- 系统监控 WebSocket (/ws/system)
"""
import os
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse

from .main import pool, collector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

admin_app = FastAPI(title="斑图生成器 - 后台管理", version="1.3.0")

# 静态文件 (admin.html)
web_dir = os.path.join(ROOT, "web")


@admin_app.get("/")
async def admin_index():
    return FileResponse(os.path.join(web_dir, "admin.html"))


# ── Worker 池配置 API ───────────────────────────────────

@admin_app.get("/api/pool/config")
async def get_pool_config():
    config = pool.get_config()
    return {
        "worker_count": config.get("worker_count", 1),
        "use_gpu": config.get("use_gpu", True),
        "max_iterations": config.get("max_iterations", 20000),
    }


@admin_app.put("/api/pool/config")
async def update_pool_config(request: Request):
    data = await request.json()
    new_config = {}
    if "worker_count" in data:
        new_config["worker_count"] = max(1, min(8, int(data["worker_count"])))
    if "use_gpu" in data:
        new_config["use_gpu"] = bool(data["use_gpu"])
    if "max_iterations" in data:
        new_config["max_iterations"] = max(100, min(100000, int(data["max_iterations"])))

    pool.reconfigure(new_config)
    return {"status": "ok", "config": pool.get_config()}


@admin_app.post("/api/pool/restart")
async def restart_pool():
    pool.restart()
    return {"status": "ok"}


@admin_app.get("/api/pool/workers")
async def get_workers():
    return {"workers": pool.get_workers_status()}


# ── 系统监控 API ────────────────────────────────────────

@admin_app.get("/api/system/current")
async def get_system_current():
    return collector.get_current()


@admin_app.get("/api/system/history")
async def get_system_history(minutes: int = 10):
    return collector.get_history(minutes=minutes)


# ── WebSocket ────────────────────────────────────────────

@admin_app.websocket("/ws/system")
async def ws_system(websocket: WebSocket):
    """高频系统监控推送（每 1 秒）"""
    await websocket.accept()
    try:
        while True:
            current = collector.get_current()
            await websocket.send_json(current)

            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
