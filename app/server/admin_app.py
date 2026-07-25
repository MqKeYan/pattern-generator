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

import psutil
import torch

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse

from .shared import StaticFiles, pool, collector
from app import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

admin_app = FastAPI(title="斑图生成器 - 后台管理", version=__version__)

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


# ── 硬件检测 API ────────────────────────────────────────
# 一次性查询，结果缓存（硬件不会变）
_hardware_cache = None


def _detect_hardware():
    """检测硬件并计算推荐的 Worker 范围"""
    cpu_physical = psutil.cpu_count(logical=False) or 1
    cpu_logical = psutil.cpu_count(logical=True) or 1
    total_ram_gb = round(psutil.virtual_memory().total / 1024**3, 1)

    gpu_count = 0
    gpu_name = ""
    vram_total_gb = 0
    try:
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else ""
            # 查询单卡显存总量
            if gpu_count > 0:
                vram_total_gb = round(
                    torch.cuda.get_device_properties(0).total_memory / 1024**3, 1
                )
    except Exception:
        pass

    # 计算推荐范围
    if gpu_count > 0 and vram_total_gb > 0:
        # 每 Worker 约需 2GB 显存
        rec_min = gpu_count
        rec_max = max(gpu_count, min(8, int(vram_total_gb / 2)))
    else:
        rec_min = 1
        rec_max = max(1, cpu_physical - 1)

    return {
        "cpu_physical": cpu_physical,
        "cpu_logical": cpu_logical,
        "total_ram_gb": total_ram_gb,
        "gpu_count": gpu_count,
        "gpu_name": gpu_name,
        "vram_total_gb": vram_total_gb,
        "rec_min": rec_min,
        "rec_max": rec_max,
        "has_gpu": gpu_count > 0,
    }


@admin_app.get("/api/system/hardware")
async def get_hardware():
    global _hardware_cache
    if _hardware_cache is None:
        _hardware_cache = _detect_hardware()
    return _hardware_cache


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


# 静态文件挂载 — 必须放在所有路由最后，否则会拦截 API 请求
if os.path.isdir(web_dir):
    admin_app.mount("/", StaticFiles(directory=web_dir), name="admin_static")
