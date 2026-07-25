"""
主站 FastAPI 应用
===============
端口 :8000，提供：
- 静态文件服务 (web/)
- 斑图模拟 API (/api/*)
- 系统状态 WebSocket (/ws/*)

与 admin_app.py 共享 PoolManager 和 SystemCollector 实例。
"""
import os
import time
import json
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse

from .shared import StaticFiles, pool, collector, store
from app import __version__

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 创建主站 APP ─────────────────────────────────────────
app = FastAPI(title="斑图生成器", version=__version__)

# 静态文件
web_dir = os.path.join(ROOT, "web")
if os.path.isdir(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

# ── WebSocket 连接管理 ──────────────────────────────────
status_connections = set()
job_connections = {}  # session_id -> set of WebSocket

# 记录启动时间
_app_start_time = time.time()


# ── 生命周期事件 ─────────────────────────────────────────
@app.on_event("startup")
async def startup():
    """应用启动时启动 Worker 池和采集器"""
    pool.start()
    collector.start()

    # pool 状态变更 → 推送 WebSocket
    def on_job_change(job_id, status):
        session_id = pool.job_sessions.get(job_id, "")
        msg = json.dumps({"job_id": job_id, "status": status})
        ws_set = job_connections.get(session_id, set())
        for ws in list(ws_set):
            try:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(msg), asyncio.get_event_loop()
                )
            except Exception:
                pass

    pool.on_status_change = on_job_change


@app.on_event("shutdown")
async def shutdown():
    pool.stop()
    collector.stop()


# ── API 路由 ──────────────────────────────────────────────

@app.get("/api/version")
async def get_version():
    """返回当前版本号"""
    return {"version": __version__}


@app.get("/api/session")
async def get_session():
    """返回 session_id（前端通过 localStorage 维护）"""
    return {"session_id": ""}


@app.get("/api/models")
async def get_models():
    """返回所有模型列表和完整配置"""
    from app.engine.config import MODEL_CONFIGS, MODEL_INIT_RANGES, PARAM_MEANINGS
    return {
        "models": list(MODEL_CONFIGS.keys()),
        "configs": {k: {
            "params": v["params"],
            "defaults": v["defaults"],
            "recommended_iterations": v["recommended_iterations"],
            "description": v["description"],
        } for k, v in MODEL_CONFIGS.items()},
        "init_ranges": MODEL_INIT_RANGES,
        "param_meanings": PARAM_MEANINGS,
    }


@app.get("/api/models/{model_id}")
async def get_model(model_id: str):
    """返回单个模型的默认参数"""
    from app.engine.config import MODEL_CONFIGS, MODEL_INIT_RANGES, PARAM_MEANINGS
    config = MODEL_CONFIGS.get(model_id)
    if config is None:
        return JSONResponse({"error": f"模型 '{model_id}' 不存在"}, status_code=404)
    return {
        "config": config,
        "init_range": MODEL_INIT_RANGES.get(model_id),
        "param_meanings": PARAM_MEANINGS.get(model_id),
    }


@app.post("/api/jobs")
async def create_job(request: Request):
    """提交任务"""
    data = await request.json()
    data.setdefault("session_id", "anonymous")
    data.setdefault("track_points", [])

    # 校验迭代数限制
    max_iter = pool.config.get("max_iterations", 20000)
    if data.get("iterations", 0) > max_iter:
        data["iterations"] = max_iter

    job_id = pool.submit_job(data)

    # 计算队列位置
    pos = 1
    with pool._lock:
        for i, j in enumerate(pool.pending_jobs):
            if j["job_id"] == job_id:
                pos = i + 1
                break

    return {
        "job_id": job_id,
        "status": "queued",
        "position": pos,
    }


@app.get("/api/jobs")
async def list_jobs(session_id: str = ""):
    """列出某 session 的所有任务"""
    if not session_id:
        return {"jobs": []}
    return {"jobs": pool.get_session_jobs(session_id)}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """获取任务状态或结果"""
    status = pool.get_job_status(job_id)
    if status is None:
        return JSONResponse({"error": "任务不存在"}, status_code=404)

    resp = {"job_id": job_id, **status}
    if status.get("status") == "completed":
        result = pool.get_result(job_id)
        if result:
            resp["result"] = result
    return resp


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    """取消/删除任务，同时清理结果数据"""
    cancelled = pool.cancel_job(job_id)
    if cancelled:
        store.delete(job_id)
        return {"status": "cancelled"}
    return JSONResponse({"error": "无法取消运行中的任务"}, status_code=400)


# ── WebSocket ────────────────────────────────────────────

@app.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    """系统状态推送（每 3 秒）"""
    await websocket.accept()
    status_connections.add(websocket)
    try:
        while True:
            uptime_sec = int(time.time() - _app_start_time)
            h, m, s = uptime_sec // 3600, (uptime_sec % 3600) // 60, uptime_sec % 60
            current = collector.get_current()

            payload = {
                "uptime": f"{h:02d}:{m:02d}:{s:02d}",
                "cpu_percent": current.get("cpu_percent", 0),
                "gpu_percent": current.get("gpu_percent", 0),
                "memory_mb": current.get("system_memory_mb", 0),
                "workers_total": len(pool.workers),
                "workers_busy": sum(1 for w in pool.get_workers_status() if w["status"] == "busy"),
                "queue_length": pool.get_queue_length(),
            }
            await websocket.send_json(payload)
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
    finally:
        status_connections.discard(websocket)


# /ws/jobs — 预留给未来前端任务状态推送功能，当前未连接
