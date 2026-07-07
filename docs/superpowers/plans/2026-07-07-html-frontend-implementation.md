# HTML 前端改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 tkinter 桌面斑图生成器改造为前后端分离的 HTML 应用，主站 :8000 + 后台管理 :8010，仅局域网使用。

**Architecture:** FastAPI 双端口服务，共享进程内 Worker 池。主站提供模拟任务提交和 Plotly.js 图表展示，后台管理提供 Worker 池配置和实时系统监控。前端纯静态 HTML + Vue 3 CDN。

**Tech Stack:** FastAPI + WebSocket + Vue 3 + Tailwind CSS + Plotly.js + Chart.js + multiprocessing

**项目结构变更:**
```
斑图生成器/
├── app/                    # 保持不变 (simulator.py, models.py, config.py)
├── server/                 # 新增: FastAPI 后端
│   ├── __init__.py
│   ├── main.py             # 主站 FastAPI 应用 (:8000)
│   ├── admin_app.py        # 后台管理 FastAPI 应用 (:8010)
│   ├── pool.py             # Worker 进程池管理
│   ├── worker.py           # 子进程入口
│   ├── collector.py        # 系统监控采集
│   └── store.py            # 结果存储
├── web/                    # 新增: 前端静态文件
│   ├── index.html           # 主站页面
│   ├── admin.html           # 后台管理页面
│   └── js/
│       ├── app.js           # 主站 Vue 逻辑
│       └── admin.js         # 后台管理 Vue 逻辑
├── start.py                # 新增: 一键启动
└── requirements.txt        # 更新依赖
```

---

### Task 1: 安装依赖并创建目录结构

**Files:**
- Modify: `requirements.txt`
- Create: `server/__init__.py`
- Create: `server/` 目录
- Create: `web/js/` 目录

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p "D:/斑图生成器/server"
mkdir -p "D:/斑图生成器/web/js"
```

- [ ] **Step 2: 创建 server/__init__.py**

```python
# server 包
```

- [ ] **Step 3: 更新 requirements.txt**

```
# 斑图生成器 — Python 依赖清单
# 安装: pip install -r requirements.txt

# 核心计算引擎（GPU/CPU 混合计算，CUDA 可选）
torch>=2.0.0

# 数值计算（数组操作、网格构建、统计）
numpy>=1.24.0

# 系统监控（CPU/内存/GPU 使用率）
psutil>=5.9.0

# Web 框架
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
aiofiles>=23.0.0
```

---

### Task 2: Worker 进程 — worker.py

**Files:**
- Create: `server/worker.py`

子进程入口。每个 worker 独立持有 PatternSimulator，通过 Pipe 接收任务、返回结果。

- [ ] **Step 1: 编写 worker.py**

```python
"""
Worker 进程
==========
子进程入口：接收任务 → 执行模拟 → 返回结果。
每个 worker 独立加载 PyTorch 模拟器，独占 GPU 上下文。
"""
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import torch
import numpy as np
from app.simulator import PatternSimulator


def worker_loop(pipe, worker_id, use_cuda):
    """子进程主循环

    pipe: multiprocessing.Connection — 与主进程的双向通信管道
    worker_id: int — 工作器编号
    use_cuda: bool — 是否尝试使用 GPU
    """
    if use_cuda and torch.cuda.is_available():
        if torch.cuda.device_count() > 1:
            torch.cuda.set_device(worker_id % torch.cuda.device_count())

    simulator = PatternSimulator(grid_size=100, use_cuda=use_cuda)
    print(f"[Worker {worker_id}] 初始化完成，设备: {simulator.hardware_info}")

    while True:
        msg = pipe.recv()
        if msg is None:
            break

        try:
            job = msg
            job_id = job["job_id"]

            pipe.send({"type": "progress", "job_id": job_id, "progress": 0})

            # 执行模拟
            if job["job_type"] == "simulate":
                n_iter = min(job["iterations"], 20000)

                # 进度回传
                def progress_callback(p):
                    pipe.send({"type": "progress", "job_id": job_id, "progress": p})
                # 模拟调用
                x_data, y_data, evolution = simulator.simulate(
                    job["model"],
                    job["params"],
                    n_iter,
                    tuple(job["init_x_range"]),
                    tuple(job["init_y_range"]),
                    job.get("track_points", []),
                )

                # 转为可序列化格式
                result = {
                    "x_data": x_data.tolist(),
                    "y_data": y_data.tolist(),
                    "evolution": _evolution_to_dict(evolution),
                    "hardware_info": simulator.hardware_info,
                }
            elif job["job_type"] == "animate":
                n_frames = min(job.get("frames", 300), 1000)

                def progress_callback(p):
                    pipe.send({"type": "progress", "job_id": job_id, "progress": p})

                x_hist, y_hist = simulator.simulate_with_history(
                    job["model"],
                    job["params"],
                    n_frames,
                    tuple(job["init_x_range"]),
                    tuple(job["init_y_range"]),
                )

                result = {
                    "x_history": x_hist.tolist(),
                    "y_history": y_hist.tolist(),
                    "hardware_info": simulator.hardware_info,
                }

            pipe.send({"type": "result", "job_id": job_id, "result": result})

        except Exception as e:
            import traceback
            pipe.send({
                "type": "error",
                "job_id": job.get("job_id", "unknown"),
                "error": str(e),
                "traceback": traceback.format_exc(),
            })

    print(f"[Worker {worker_id}] 已退出")


def _evolution_to_dict(evolution):
    """将 evolution 内嵌的 list 转成纯 Python 类型"""
    result = {}
    for key, val in evolution.items():
        result[key] = {
            "x": [float(v) for v in val["x"]],
            "y": [float(v) for v in val["y"]],
        }
    return result
```

---

### Task 3: 系统监控采集 — collector.py

**Files:**
- Create: `server/collector.py`

每 1 秒采集 CPU/GPU/内存数据，供后台管理使用。

- [ ] **Step 1: 编写 collector.py**

```python
"""
系统监控采集模块
==============
定时采集 CPU、GPU、内存、Worker 负载数据。
"""
import time
import psutil
import os
import threading
from collections import deque


class SystemCollector:
    """系统监控采集器

    后台线程每秒采集一次系统指标，保留近 10 分钟历史数据。

    用法:
        collector = SystemCollector(pool_manager)
        collector.start()
        history = collector.get_history(minutes=5)
    """

    def __init__(self, pool_manager=None):
        self.pool = pool_manager
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # 历史数据 (最多 600 个点 = 10 分钟)
        self.timestamps = deque(maxlen=600)
        self.cpu = deque(maxlen=600)
        self.gpu = deque(maxlen=600)
        self.gpu_mem = deque(maxlen=600)
        self.sys_mem = deque(maxlen=600)

    def start(self):
        """启动采集线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止采集线程"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        while self._running:
            try:
                self._collect()
            except Exception:
                pass
            time.sleep(1)

    def _collect(self):
        now = time.strftime("%H:%M:%S")
        cpu_pct = psutil.cpu_percent(interval=None)
        cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        sys_mem_total = psutil.virtual_memory().total / 1024 / 1024

        gpu_pct = 0.0
        gpu_mem = 0.0
        try:
            import torch
            if torch.cuda.is_available():
                gpu_pct = torch.cuda.utilization()
                gpu_mem = torch.cuda.memory_allocated() / 1024**2
        except Exception:
            pass

        workers_info = []
        if self.pool:
            workers_info = self.pool.get_workers_status()

        with self._lock:
            self.timestamps.append(now)
            self.cpu.append(cpu_pct)
            self.gpu.append(gpu_pct)
            self.gpu_mem.append(gpu_mem)
            self.sys_mem.append(mem)

        self._current = {
            "timestamp": now,
            "cpu_percent": cpu_pct,
            "cpu_per_core": cpu_per_core,
            "gpu_percent": gpu_pct,
            "gpu_memory_mb": gpu_mem,
            "gpu_memory_total_mb": 8192,
            "system_memory_mb": mem,
            "system_memory_total_mb": sys_mem_total,
            "workers": workers_info,
            "queue_length": len(self.pool.pending_jobs) if self.pool else 0,
        }

    def get_current(self):
        """获取当前瞬时值"""
        return getattr(self, "_current", {})

    def get_history(self, minutes=10):
        """获取近几分钟的历史数据"""
        max_points = minutes * 60
        with self._lock:
            n = min(len(self.timestamps), max_points)
            return {
                "timestamps": list(self.timestamps)[-n:],
                "cpu": list(self.cpu)[-n:],
                "gpu": list(self.gpu)[-n:],
                "memory_mb": list(self.sys_mem)[-n:],
            }
```

---

### Task 4: 结果存储 — store.py

**Files:**
- Create: `server/store.py`

- [ ] **Step 1: 编写 store.py**

```python
"""
结果存储模块
==========
内存 + 文件两级结果缓存，带 TTL 过期和 session 配额管理。
"""
import time
import os
import threading
import json

_temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp", "results")


class ResultStore:
    """任务结果存储

    小结果 (< 10MB) 保持在内存，大结果写入文件。
    TTL 1 小时后自动清理。每个 session 最多保留 20 条记录。

    用法:
        store = ResultStore()
        store.put("job-xxx", {"x_data": [...]})
        result = store.get("job-xxx")
    """

    def __init__(self, ttl_seconds=3600):
        self.ttl = ttl_seconds
        self._cache = {}        # job_id -> {data, timestamp, session_id, size}
        self._sessions = {}     # session_id -> [job_id, ...]
        self._lock = threading.Lock()

        os.makedirs(_temp_dir, exist_ok=True)

        # 后台清理线程
        self._cleaner = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleaner.start()

    def put(self, job_id, data, session_id):
        """存储任务结果"""
        size = _estimate_size(data)
        entry = {
            "data": data,
            "timestamp": time.time(),
            "session_id": session_id,
            "size": size,
            "on_disk": False,
        }

        with self._lock:
            # 大结果写入文件
            if size > 10 * 1024 * 1024:
                filepath = os.path.join(_temp_dir, f"{job_id}.json")
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                entry["data"] = None  # 释放内存
                entry["filepath"] = filepath
                entry["on_disk"] = True

            self._cache[job_id] = entry

            # session 配额管理
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            self._sessions[session_id].append(job_id)
            if len(self._sessions[session_id]) > 20:
                old_job = self._sessions[session_id].pop(0)
                self._delete(old_job)

    def get(self, job_id):
        """获取任务结果"""
        with self._lock:
            entry = self._cache.get(job_id)
            if entry is None:
                return None
            entry["timestamp"] = time.time()  # 刷新 TTL
            if entry["on_disk"]:
                with open(entry["filepath"], "r", encoding="utf-8") as f:
                    return json.load(f)
            return entry["data"]

    def delete(self, job_id):
        """删除任务结果"""
        with self._lock:
            self._delete(job_id)

    def _delete(self, job_id):
        entry = self._cache.pop(job_id, None)
        if entry and entry.get("on_disk"):
            try:
                os.remove(entry["filepath"])
            except OSError:
                pass

    def _cleanup_loop(self):
        while True:
            time.sleep(60)
            now = time.time()
            with self._lock:
                expired = [jid for jid, e in self._cache.items()
                           if now - e["timestamp"] > self.ttl]
                for jid in expired:
                    self._delete(jid)


def _estimate_size(data):
    """估算数据大小（字节）"""
    try:
        return len(json.dumps(data, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0
```

---

### Task 5: Worker 进程池管理 — pool.py

**Files:**
- Create: `server/pool.py`

- [ ] **Step 1: 编写 pool.py**

```python
"""
Worker 进程池管理
===============
管理子进程的创建、销毁、任务分发和状态查询。
主进程维护一个 asyncio.Queue 作为待办队列，空闲 worker 领取任务。
"""
import multiprocessing as mp
import threading
import time
import uuid
from collections import deque


class PoolManager:
    """Worker 进程池

    用法:
        pool = PoolManager()
        pool.start(worker_count=2, use_gpu=True)
        job_id = pool.submit_job({"job_type": "simulate", ...})
        result = pool.get_result(job_id)
        pool.stop()
    """

    def __init__(self, store=None):
        self.store = store
        self.workers = []         # [(process, pipe)]
        self.pending_jobs = deque()  # 待办队列
        self.idle_workers = deque()   # 空闲 worker 的 pipe

        self._running = False
        self._lock = threading.Lock()
        self._result_thread = None

        # 任务状态
        self.job_statuses = {}  # job_id -> {"status": str, "progress": int, ...}
        self.job_sessions = {}  # job_id -> session_id
        self.worker_jobs = {}   # worker_id -> job_id

        # 配置
        self.config = {
            "worker_count": 1,
            "use_gpu": True,
            "max_iterations": 20000,
        }

        # 状态变更回调 (WebSocket 推送用)
        self.on_status_change = None  # callable(job_id, status)

    def start(self, worker_count=None, use_gpu=None):
        """启动 Worker 池"""
        if self._running:
            return

        if worker_count is not None:
            self.config["worker_count"] = worker_count
        if use_gpu is not None:
            self.config["use_gpu"] = use_gpu

        self._running = True
        self._spawn_workers()
        self._result_thread = threading.Thread(target=self._result_loop, daemon=True)
        self._result_thread.start()

    def _spawn_workers(self):
        for i in range(self.config["worker_count"]):
            parent_pipe, child_pipe = mp.Pipe()
            proc = mp.Process(
                target=_worker_entry,
                args=(child_pipe, i, self.config["use_gpu"]),
                daemon=True,
            )
            proc.start()
            child_pipe.close()
            self.workers.append((proc, parent_pipe))
            self.idle_workers.append((i, parent_pipe))

    def submit_job(self, job_data):
        """提交任务，返回 job_id"""
        job_id = str(uuid.uuid4())
        job_data = dict(job_data)
        job_data["job_id"] = job_id

        with self._lock:
            self.job_statuses[job_id] = {"status": "queued", "progress": 0}
            self.job_sessions[job_id] = job_data.get("session_id", "")
            self.pending_jobs.append(job_data)

        self._dispatch()
        return job_id

    def _dispatch(self):
        """尝试将待办任务分配给空闲 worker"""
        while self.idle_workers and self.pending_jobs:
            wid, pipe = self.idle_workers.popleft()
            job = self.pending_jobs.popleft()
            job_id = job["job_id"]

            with self._lock:
                self.job_statuses[job_id]["status"] = "running"
                self.worker_jobs[wid] = job_id

            pipe.send(job)

            if self.on_status_change:
                self.on_status_change(job_id, "running")

    def _result_loop(self):
        """监听所有 worker 的结果管道（后台线程）"""
        while self._running:
            for wid, (proc, pipe) in enumerate(self.workers):
                if not pipe.poll(0.01):
                    continue
                try:
                    msg = pipe.recv()
                except (EOFError, OSError):
                    continue

                msg_type = msg.get("type")
                job_id = msg.get("job_id")

                if msg_type == "progress":
                    with self._lock:
                        if job_id in self.job_statuses:
                            self.job_statuses[job_id]["progress"] = msg["progress"]

                elif msg_type == "result":
                    result = msg["result"]
                    with self._lock:
                        self.job_statuses[job_id]["status"] = "completed"
                        self.job_statuses[job_id]["progress"] = 100
                        sid = self.job_sessions.get(job_id, "")
                    if self.store:
                        self.store.put(job_id, result, sid)
                    if self.on_status_change:
                        self.on_status_change(job_id, "completed")

                    # 回收 worker
                    with self._lock:
                        self.worker_jobs.pop(wid, None)
                    self.idle_workers.append((wid, pipe))
                    self._dispatch()

                elif msg_type == "error":
                    with self._lock:
                        self.job_statuses[job_id]["status"] = "error"
                        self.job_statuses[job_id]["error"] = msg.get("error", "")
                    if self.on_status_change:
                        self.on_status_change(job_id, "error")

                    with self._lock:
                        self.worker_jobs.pop(wid, None)
                    self.idle_workers.append((wid, pipe))
                    self._dispatch()

    def get_result(self, job_id):
        """获取任务结果"""
        if self.store:
            return self.store.get(job_id)
        return None

    def get_job_status(self, job_id):
        """获取任务状态"""
        with self._lock:
            s = self.job_statuses.get(job_id)
            if s is None:
                return None
            return dict(s)

    def get_session_jobs(self, session_id):
        """获取某 session 的所有任务"""
        with self._lock:
            return [{"job_id": jid, **self.job_statuses[jid]}
                    for jid, sid in self.job_sessions.items()
                    if sid == session_id]

    def cancel_job(self, job_id):
        """取消排队中的任务"""
        with self._lock:
            # 检查是否在待办队列
            for i, job in enumerate(self.pending_jobs):
                if job["job_id"] == job_id:
                    self.pending_jobs.remove(job)
                    self.job_statuses[job_id]["status"] = "cancelled"
                    if self.on_status_change:
                        self.on_status_change(job_id, "cancelled")
                    return True
            # 运行中的任务无法取消（PyTorch 不支持中断）
            if self.job_statuses.get(job_id, {}).get("status") == "running":
                return False
            return False

    def get_workers_status(self):
        """获取所有 worker 状态"""
        result = []
        with self._lock:
            for wid, (proc, _) in enumerate(self.workers):
                job_id = self.worker_jobs.get(wid)
                status = "busy" if job_id else "idle"
                progress = self.job_statuses[job_id]["progress"] if job_id and job_id in self.job_statuses else None
                result.append({
                    "id": wid,
                    "status": status,
                    "job_id": job_id,
                    "progress": progress,
                })
        return result

    def reconfigure(self, new_config):
        """更新配置 (需重启生效)"""
        with self._lock:
            self.config.update(new_config)

    def restart(self):
        """重启 Worker 池"""
        self.stop()
        time.sleep(0.5)
        self.start()

    def stop(self):
        """停止所有 Worker"""
        self._running = False
        for _, pipe in self.workers:
            try:
                pipe.send(None)
            except Exception:
                pass
        for proc, _ in self.workers:
            proc.join(timeout=3)
            if proc.is_alive():
                proc.terminate()
        self.workers.clear()
        self.idle_workers.clear()
        self.worker_jobs.clear()

    def get_queue_length(self):
        """获取待办队列长度"""
        with self._lock:
            return len(self.pending_jobs)

    def get_config(self):
        """获取当前配置"""
        with self._lock:
            return dict(self.config)


def _worker_entry(pipe, worker_id, use_cuda):
    """子进程入口—包装 worker_loop"""
    from server.worker import worker_loop
    worker_loop(pipe, worker_id, use_cuda)
```

---

### Task 6: 主站 FastAPI 应用 — main.py

**Files:**
- Create: `server/main.py`

- [ ] **Step 1: 编写 main.py**

```python
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
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from .pool import PoolManager
from .store import ResultStore
from .collector import SystemCollector

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 共享实例 ──────────────────────────────────────────────
store = ResultStore()
pool = PoolManager(store=store)
collector = SystemCollector(pool=pool)

# ── 创建主站 APP ─────────────────────────────────────────
app = FastAPI(title="斑图生成器", version="1.3.0")

# 静态文件
web_dir = os.path.join(ROOT, "web")
if os.path.isdir(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

# ── WebSocket 连接管理 ──────────────────────────────────
status_connections = set()
job_connections = {}  # session_id -> set of WebSocket


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
        # 推送给 session 相关的连接
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

@app.get("/api/session")
async def get_session(request: Request):
    """返回 session_id（前端通过 localStorage 维护）"""
    return {"session_id": ""}  # 前端自己管理


@app.get("/api/models")
async def get_models():
    """返回所有模型列表和完整配置"""
    from app.config import MODEL_CONFIGS, MODEL_INIT_RANGES, PARAM_MEANINGS
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
    from app.config import MODEL_CONFIGS, MODEL_INIT_RANGES, PARAM_MEANINGS
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
    pos = list(pool.pending_jobs).index(
        next((j for j in pool.pending_jobs if j["job_id"] == job_id), None)
    ) if any(j["job_id"] == job_id for j in pool.pending_jobs) else 0

    return {
        "job_id": job_id,
        "status": "queued",
        "position": pos + 1,
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
    """取消/删除任务"""
    cancelled = pool.cancel_job(job_id)
    if cancelled:
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
            uptime_sec = int(time.time() - _get_start_time())
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


@app.websocket("/ws/jobs/{session_id}")
async def ws_jobs(websocket: WebSocket, session_id: str):
    """特定 session 的任务状态推送"""
    await websocket.accept()
    if session_id not in job_connections:
        job_connections[session_id] = set()
    job_connections[session_id].add(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            if await websocket.receive_text():
                pass
    except WebSocketDisconnect:
        pass
    finally:
        job_connections[session_id].discard(websocket)
        if not job_connections[session_id]:
            del job_connections[session_id]


# ── 辅助函数 ─────────────────────────────────────────────

_start_time = time.time


def _get_start_time():
    return _start_time()
```

---

### Task 7: 后台管理 FastAPI 应用 — admin_app.py

**Files:**
- Create: `server/admin_app.py`

- [ ] **Step 1: 编写 admin_app.py**

```python
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
import time
import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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

            # 等待 1 秒，同时检测断开
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
```

---

### Task 8: 一键启动脚本 — start.py

**Files:**
- Create: `start.py`

- [ ] **Step 1: 编写 start.py**

```python
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
```

---

### Task 9: 主站前端 — index.html

**Files:**
- Create: `web/index.html`

- [ ] **Step 1: 编写 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>斑图生成器</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: {
      colors: {
        'dt-bg-root': '#0B1120', 'dt-bg': '#0F172A',
        'dt-bg-elevated': '#1E293B', 'dt-bg-input': '#1A2332',
        'dt-bg-hover': '#334155', 'dt-border': '#1E3A5F',
        'dt-border-focus': '#3B82F6', 'dt-text': '#F1F5F9',
        'dt-text-secondary': '#94A3B8', 'dt-text-muted': '#64748B',
        'dt-primary': '#3B82F6', 'dt-primary-light': '#60A5FA',
        'dt-success': '#22C55E', 'dt-danger': '#EF4444',
        'dt-warning': '#F59E0B',
      }
    }
  }
}
</script>
<script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body class="bg-dt-bg-root text-dt-text font-sans m-0 p-0 h-screen overflow-hidden">

<div id="app" class="h-screen flex flex-col">
  <!-- 状态栏 -->
  <div class="h-8 bg-dt-bg-root text-dt-text-muted text-xs flex items-center px-3 shrink-0 border-b border-dt-border/30">
    <span v-for="(seg, i) in statusSegments" :key="i">
      <span v-if="i > 0" class="mx-2 text-dt-border">|</span>
      <span>{{ seg }}</span>
    </span>
  </div>

  <!-- 主体 -->
  <div class="flex flex-1 min-h-0">
    <!-- 左侧面板 -->
    <div class="w-72 bg-dt-bg shrink-0 overflow-y-auto border-r border-dt-border/30 p-2 space-y-2">
      <!-- 模型设置 -->
      <div class="border border-dt-border rounded p-2">
        <div class="text-dt-primary-light text-xs font-bold mb-1">模型设置</div>
        <select v-model="currentModel" @change="onModelChange"
                class="w-full bg-dt-bg-input border border-dt-border rounded px-2 py-1 text-xs text-dt-text mb-1">
          <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
        </select>
        <div class="flex gap-2 text-xs">
          <span class="text-dt-text-secondary">迭代</span>
          <input v-model.number="iterations" type="number" class="w-16 bg-dt-bg-input border border-dt-border rounded px-1 text-center" min="100" max="20000">
          <span class="text-dt-text-secondary">帧数</span>
          <input v-model.number="frames" type="number" class="w-14 bg-dt-bg-input border border-dt-border rounded px-1 text-center" min="10" max="1000">
        </div>
      </div>

      <!-- 参数设置 -->
      <div class="border border-dt-border rounded p-2">
        <div class="text-dt-primary-light text-xs font-bold mb-1">参数设置</div>
        <div v-for="(p, i) in currentParams" :key="i" class="flex items-center gap-1 mb-0.5">
          <span class="text-dt-text-secondary text-xs w-28 truncate" :title="p.name">{{ p.name }}</span>
          <input v-model.number="params[i]" type="number" step="any"
                 class="flex-1 bg-dt-bg-input border border-dt-border rounded px-1 py-0.5 text-xs text-center">
          <button @click="resetParam(i)" class="text-xs text-dt-text-muted hover:text-dt-primary px-1">重置</button>
        </div>
        <button @click="resetAllParams" class="w-full text-xs text-dt-text-muted hover:text-dt-primary mt-1">重置为默认值</button>
      </div>

      <!-- 初始值范围 -->
      <div class="border border-dt-border rounded p-2">
        <div class="text-dt-primary-light text-xs font-bold mb-1">初始值范围</div>
        <div class="text-dt-text-secondary text-xs mb-1">{{ initDesc }}</div>
        <div v-for="item in initRanges" :key="item.key" class="flex items-center gap-1 mb-0.5">
          <span class="text-dt-text-secondary text-xs w-20">{{ item.label }}</span>
          <input v-model.number="item.value" type="number" step="0.01"
                 class="flex-1 bg-dt-bg-input border border-dt-border rounded px-1 py-0.5 text-xs text-center">
          <button @click="resetInit(item.key)" class="text-xs text-dt-text-muted hover:text-dt-primary px-1">重置</button>
        </div>
        <button @click="applyBestInit" class="w-full text-xs text-dt-text-muted hover:text-dt-primary mt-1">应用最佳初始值</button>
      </div>

      <!-- 跟踪点 -->
      <div class="border border-dt-border rounded p-2">
        <div class="text-dt-primary-light text-xs font-bold mb-1">跟踪点</div>
        <div class="flex gap-1 items-center mb-1">
          <span class="text-xs text-dt-text-secondary">X</span>
          <input v-model.number="trackX" type="number" class="w-12 bg-dt-bg-input border border-dt-border rounded px-1 text-xs text-center">
          <span class="text-xs text-dt-text-secondary">Y</span>
          <input v-model.number="trackY" type="number" class="w-12 bg-dt-bg-input border border-dt-border rounded px-1 text-xs text-center">
          <button @click="addTrackPoint" class="text-xs bg-dt-primary text-white rounded px-2 py-0.5">+</button>
          <button @click="clearTrackPoints" class="text-xs text-dt-text-muted hover:text-dt-danger px-1">清空</button>
        </div>
        <div class="text-xs text-dt-text-muted">{{ trackDisplay }}</div>
      </div>

      <!-- 任务状态 -->
      <div class="border border-dt-border rounded p-2">
        <div class="text-dt-primary-light text-xs font-bold mb-1">任务状态</div>
        <div v-if="currentJobId" class="mb-1">
          <div class="text-xs text-dt-text-secondary mb-1">{{ jobStatusText }}</div>
          <div v-if="['running','queued'].includes(jobStatus)" class="w-full bg-dt-bg-input rounded h-2">
            <div class="bg-dt-primary h-2 rounded transition-all duration-300" :style="{width: jobProgress+'%'}"></div>
          </div>
        </div>
        <div v-else class="text-xs text-dt-text-muted">暂无运行中的任务</div>
      </div>

      <!-- 控制按钮 -->
      <div class="border border-dt-border rounded p-2">
        <div class="text-dt-primary-light text-xs font-bold mb-1">控制</div>
        <div class="flex gap-2">
          <button @click="runSimulation" :disabled="isSimulating"
                  class="flex-1 bg-dt-primary text-white text-xs rounded py-1.5 disabled:opacity-50 hover:bg-dt-primary-light">运行</button>
          <button @click="resetAll" class="flex-1 border border-dt-border text-dt-text-secondary text-xs rounded py-1.5 hover:bg-dt-bg-hover">重置</button>
          <button @click="startAnimation" :disabled="!jobResult"
                  class="flex-1 bg-dt-success text-white text-xs rounded py-1.5 disabled:opacity-50">播放</button>
        </div>
      </div>
    </div>

    <!-- 右侧标签页区 -->
    <div class="flex-1 bg-dt-bg flex flex-col min-w-0">
      <div class="flex border-b border-dt-border/30 shrink-0">
        <button v-for="(tab, i) in tabs" :key="i"
                @click="activeTab = i"
                :class="activeTab === i ? 'bg-dt-primary text-white' : 'bg-dt-bg-elevated text-dt-text-secondary hover:text-dt-text'"
                class="px-6 py-2 text-xs font-medium border-r border-dt-border/30 transition-colors">
          {{ tab }}
        </button>
      </div>
      <div class="flex-1 min-h-0 p-2">
        <div id="plot-container" class="w-full h-full"></div>
      </div>
    </div>
  </div>
</div>

<script src="js/app.js"></script>
</body>
</html>
```

---

### Task 10: 主站前端逻辑 — app.js

**Files:**
- Create: `web/js/app.js`

- [ ] **Step 1: 编写 app.js**

```javascript
const { createApp, ref, reactive, computed, watch, onMounted, onUnmounted } = Vue;

createApp({
  setup() {
    // ── 状态 ─────────────────────────────────────────
    const models = ref([]);
    const modelConfigs = ref({});
    const initRangesAll = ref({});
    const paramMeanings = ref({});

    const currentModel = ref('模型1');
    const params = ref([]);
    const iterations = ref(9000);
    const frames = ref(300);
    const initDesc = ref('');

    // 初始值范围
    const xMin = ref(0.95);
    const xMax = ref(1.05);
    const yMin = ref(0.80);
    const yMax = ref(1.0);

    // 跟踪点
    const trackX = ref(50);
    const trackY = ref(50);
    const trackPoints = ref([]);

    // 任务
    const currentJobId = ref(null);
    const jobStatus = ref(null);
    const jobProgress = ref(0);
    const jobResult = ref(null);
    const isSimulating = computed(() => jobStatus.value === 'running' || jobStatus.value === 'queued');

    // 系统状态
    const uptime = ref('00:00:00');
    const cpuPercent = ref(0);
    const gpuPercent = ref(0);
    const memMb = ref(0);
    const workersBusy = ref(0);
    const workersTotal = ref(0);
    const queueLength = ref(0);

    const activeTab = ref(0);
    const tabs = ['二维斑图', '三维斑图', '动画演示'];

    // ── session ──────────────────────────────────────
    const sessionId = ref(localStorage.getItem('pattern_session_id') || crypto.randomUUID());
    localStorage.setItem('pattern_session_id', sessionId.value);

    // ── 计算属性 ────────────────────────────────────
    const currentParams = computed(() => {
      const config = modelConfigs.value[currentModel.value];
      if (!config) return [];
      return config.params.map((name, i) => ({
        name: (paramMeanings.value[currentModel.value]?.[name] || `参数${i+1}`) + ':',
        key: name,
      }));
    });

    const statusSegments = computed(() => [
      '版本号: 1.3.0',
      '运行时间: ' + uptime.value,
      'CPU: ' + cpuPercent.value + '%',
      'GPU: ' + gpuPercent.value + '%',
      '内存: ' + Math.round(memMb.value) + ' MB',
      'Workers: ' + workersBusy.value + '/' + workersTotal.value + ' 忙',
      '队列: ' + queueLength.value,
    ]);

    const jobStatusText = computed(() => {
      if (jobStatus.value === 'queued') return '排队中...';
      if (jobStatus.value === 'running') return '运行中 ' + jobProgress.value + '%';
      if (jobStatus.value === 'completed') return '已完成';
      if (jobStatus.value === 'error') return '出错了';
      return '';
    });

    const initRanges = computed(() => [
      { label: 'X 最小值', value: xMin, key: 'x_min' },
      { label: 'X 最大值', value: xMax, key: 'x_max' },
      { label: 'Y 最小值', value: yMin, key: 'y_min' },
      { label: 'Y 最大值', value: yMax, key: 'y_max' },
    ]);

    const trackDisplay = computed(() => {
      if (!trackPoints.value.length) return '已添加点';
      return trackPoints.value.map(p => `(${p.x},${p.y})`).join(' ');
    });

    // ── 方法 ─────────────────────────────────────────
    async function fetchModels() {
      try {
        const res = await fetch('/api/models');
        const data = await res.json();
        models.value = data.models;
        modelConfigs.value = data.configs;
        initRangesAll.value = data.init_ranges;
        paramMeanings.value = data.param_meanings;
        syncModelDefaults();
      } catch (e) {
        console.error('加载模型失败:', e);
      }
    }

    function syncModelDefaults() {
      const config = modelConfigs.value[currentModel.value];
      if (!config) return;
      params.value = [...config.defaults];
      iterations.value = config.recommended_iterations;
      const ir = initRangesAll.value[currentModel.value];
      if (ir) {
        xMin.value = ir.x_range[0];
        xMax.value = ir.x_range[1];
        yMin.value = ir.y_range[0];
        yMax.value = ir.y_range[1];
        initDesc.value = ir.description || '';
      }
    }

    function onModelChange() {
      if (isSimulating.value) {
        alert('模拟进行中，请等待完成');
        return;
      }
      syncModelDefaults();
    }

    function resetParam(index) {
      const config = modelConfigs.value[currentModel.value];
      if (config) params.value[index] = config.defaults[index];
    }

    function resetAllParams() {
      const config = modelConfigs.value[currentModel.value];
      if (config) params.value = [...config.defaults];
    }

    function resetInit(key) {
      const ir = initRangesAll.value[currentModel.value];
      if (!ir) return;
      const map = { x_min: [ir.x_range[0], xMin], x_max: [ir.x_range[1], xMax],
                    y_min: [ir.y_range[0], yMin], y_max: [ir.y_range[1], yMax] };
      if (map[key]) map[key][1].value = map[key][0];
    }

    function applyBestInit() {
      const ir = initRangesAll.value[currentModel.value];
      if (ir) {
        xMin.value = ir.x_range[0];
        xMax.value = ir.x_range[1];
        yMin.value = ir.y_range[0];
        yMax.value = ir.y_range[1];
      }
    }

    function addTrackPoint() {
      const x = Number(trackX.value);
      const y = Number(trackY.value);
      if (x < 0 || x >= 100 || y < 0 || y >= 100) {
        alert('坐标必须在 0-99 之间');
        return;
      }
      if (trackPoints.value.some(p => p.x === x && p.y === y)) {
        alert('该点已存在');
        return;
      }
      trackPoints.value.push({ x, y });
    }

    function clearTrackPoints() {
      trackPoints.value = [];
    }

    function resetAll() {
      resetAllParams();
      applyBestInit();
      const config = modelConfigs.value[currentModel.value];
      if (config) iterations.value = config.recommended_iterations;
    }

    // ── 任务提交与轮询 ─────────────────────────────
    async function runSimulation() {
      if (isSimulating.value) return;

      currentJobId.value = null;
      jobStatus.value = null;
      jobProgress.value = 0;
      jobResult.value = null;

      const config = modelConfigs.value[currentModel.value];
      if (!config) return;

      const payload = {
        session_id: sessionId.value,
        job_type: 'simulate',
        model: currentModel.value,
        params: params.value,
        iterations: iterations.value,
        init_x_range: [xMin.value, xMax.value],
        init_y_range: [yMin.value, yMax.value],
        track_points: trackPoints.value.map(p => ({ x: p.x, y: p.y })),
      };

      try {
        const res = await fetch('/api/jobs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        currentJobId.value = data.job_id;
        jobStatus.value = 'queued';
        pollJobStatus(data.job_id);
      } catch (e) {
        console.error('提交任务失败:', e);
        jobStatus.value = 'error';
      }
    }

    async function pollJobStatus(jobId) {
      while (true) {
        try {
          const res = await fetch(`/api/jobs/${jobId}`);
          const data = await res.json();
          jobStatus.value = data.status;
          jobProgress.value = data.progress || 0;

          if (data.status === 'completed') {
            jobResult.value = data.result;
            render2D(data.result);
            return;
          }
          if (data.status === 'error') {
            console.error('任务失败:', data.error);
            return;
          }
          if (data.status === 'cancelled') {
            return;
          }
        } catch (e) {
          console.error('轮询失败:', e);
          return;
        }
        await new Promise(r => setTimeout(r, 1000));
      }
    }

    // ── 动画 ─────────────────────────────────────────
    async function startAnimation() {
      if (jobResult.value) {
        // 已有模拟结果，切换动画标签页
        activeTab.value = 2;
        renderAnimation(jobResult.value);
      }
    }

    // ── 渲染 ─────────────────────────────────────────
    function render2D(result) {
      activeTab.value = 0;
      const container = document.getElementById('plot-container');
      container.innerHTML = '<div id="plot-2d" class="w-full h-full"></div>';

      const xData = result.x_data;
      const yData = result.y_data;
      const evo = result.evolution;

      // 热力图布局
      const heatmapLayout = {
        paper_bgcolor: '#0F172A', plot_bgcolor: '#1E293B',
        font: { color: '#94A3B8', size: 10 },
        margin: { t: 30, r: 20, b: 30, l: 40 },
        xaxis: { showgrid: false, zeroline: false },
        yaxis: { showgrid: false, zeroline: false, scaleanchor: 'x' },
      };

      // 构建子图
      const traces = [];
      const grids = [
        { name: 'X种群', data: xData, cmap: 'Viridis', row: 1, col: 1 },
        { name: 'Y种群', data: yData, cmap: 'Plasma', row: 1, col: 2 },
      ];

      // 合并图
      const xNorm = normalize2D(xData);
      const yNorm = normalize2D(yData);
      const combined = xData.map((row, i) => row.map((_, j) => [
        xNorm[i][j], yNorm[i][j], 0
      ]));

      traces.push({
        z: xData, type: 'heatmap', colorscale: 'Viridis',
        name: 'X种群', domain: { row: 1, col: 1 },
        colorbar: { x: 0.30, len: 0.35, title: { text: '密度', font: { size: 8 } } }
      });
      traces.push({
        z: yData, type: 'heatmap', colorscale: 'Plasma',
        name: 'Y种群', domain: { row: 1, col: 2 },
        colorbar: { x: 0.63, len: 0.35, title: { text: '密度', font: { size: 8 } } }
      });
      traces.push({
        z: combined, type: 'heatmap', colorscale: 'Viridis',
        name: '合并斑图', domain: { row: 1, col: 3 },
        colorbar: { x: 0.97, len: 0.35, title: { text: '密度', font: { size: 8 } } }
      });

      // 演化曲线
      const time = evo.center.x.map((_, i) => i);
      traces.push({
        x: time, y: evo.center.x, type: 'scatter', mode: 'lines',
        name: '中心点-X', line: { color: '#60A5FA', width: 2 },
        xaxis: 'x2', yaxis: 'y2',
      });
      traces.push({
        x: time, y: evo.center.y, type: 'scatter', mode: 'lines',
        name: '中心点-Y', line: { color: '#F87171', width: 2 },
        xaxis: 'x2', yaxis: 'y2',
      });

      // 自定义跟踪点
      const trackPointsArr = trackPoints.value || [];
      const palette = ['#34D399', '#FBBF24', '#A78BFA', '#22D3EE', '#F472B6', '#FB923C'];
      trackPointsArr.forEach((pt, i) => {
        const key = `point_${pt.x}_${pt.y}`;
        const data = evo[key];
        if (!data) return;
        const c = palette[i % palette.length];
        traces.push({
          x: time, y: data.x, type: 'scatter', mode: 'lines',
          name: `(${pt.x},${pt.y})-X`, line: { color: c, width: 1.5, dash: 'dash' },
          xaxis: 'x2', yaxis: 'y2',
        });
        traces.push({
          x: time, y: data.y, type: 'scatter', mode: 'lines',
          name: `(${pt.x},${pt.y})-Y`, line: { color: palette[(i+1) % palette.length], width: 1.5, dash: 'dash' },
          xaxis: 'x2', yaxis: 'y2',
        });
      });

      const fullLayout = {
        grid: { rows: 2, columns: 3, pattern: 'independent', roworder: 'top to bottom' },
        paper_bgcolor: '#0F172A', plot_bgcolor: '#0F172A',
        font: { color: '#94A3B8', size: 10 },
        margin: { t: 20, r: 30, b: 40, l: 50 },
        xaxis2: { domain: [0, 1], title: '迭代次数' },
        yaxis2: { domain: [0, 0.35], title: '种群密度' },
        showlegend: true,
        legend: { x: 1.02, font: { size: 9 }, bgcolor: '#1E293B' },
      };

      Plotly.newPlot('plot-2d', traces, fullLayout, { responsive: true });
    }

    function normalize2D(arr) {
      let mn = Infinity, mx = -Infinity;
      arr.forEach(r => r.forEach(v => { if (v < mn) mn = v; if (v > mx) mx = v; }));
      const rng = mx - mn || 1;
      return arr.map(r => r.map(v => (v - mn) / rng));
    }

    async function startAnimation() {
      if (!jobResult.value) return;
      activeTab.value = 2;
      renderAnimation(jobResult.value);
    }

    function renderAnimation(result) {
      const container = document.getElementById('plot-container');
      container.innerHTML = '<div id="plot-anim" class="w-full h-full"></div>';
      document.getElementById('plot-anim').innerHTML = '<p class="text-dt-text-muted text-xs p-4">动画功能：后端计算历史帧数据后按帧播放</p>';
    }

    // ── WebSocket 状态 ──────────────────────────────
    let ws = null;

    function connectStatusWS() {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${location.host}/ws/status`);
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        uptime.value = data.uptime;
        cpuPercent.value = data.cpu_percent;
        gpuPercent.value = data.gpu_percent;
        memMb.value = data.memory_mb;
        workersBusy.value = data.workers_busy;
        workersTotal.value = data.workers_total;
        queueLength.value = data.queue_length;
      };
      ws.onclose = () => setTimeout(connectStatusWS, 3000);
    }

    // ── 生命周期 ────────────────────────────────────
    onMounted(() => {
      fetchModels();
      connectStatusWS();
    });

    return {
      models, modelConfigs, initRangesAll, paramMeanings,
      currentModel, params, iterations, frames, initDesc,
      xMin, xMax, yMin, yMax,
      trackX, trackY, trackPoints, trackDisplay,
      sessionId,
      currentJobId, jobStatus, jobProgress, jobResult, isSimulating,
      uptime, cpuPercent, gpuPercent, memMb,
      workersBusy, workersTotal, queueLength,
      activeTab, tabs,
      currentParams, statusSegments, jobStatusText, initRanges,
      fetchModels, onModelChange,
      resetParam, resetAllParams, resetInit, applyBestInit,
      addTrackPoint, clearTrackPoints, resetAll,
      runSimulation, startAnimation,
    };
  }
}).mount('#app');
```

---

### Task 11: 后台管理前端 — admin.html

**Files:**
- Create: `web/admin.html`

- [ ] **Step 1: 编写 admin.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>斑图生成器 - 后台管理</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: {
      colors: {
        'dt-bg-root': '#0B1120', 'dt-bg': '#0F172A',
        'dt-bg-elevated': '#1E293B', 'dt-bg-input': '#1A2332',
        'dt-bg-hover': '#334155', 'dt-border': '#1E3A5F',
        'dt-border-focus': '#3B82F6', 'dt-text': '#F1F5F9',
        'dt-text-secondary': '#94A3B8', 'dt-text-muted': '#64748B',
        'dt-primary': '#3B82F6', 'dt-primary-light': '#60A5FA',
        'dt-success': '#22C55E', 'dt-danger': '#EF4444',
        'dt-warning': '#F59E0B',
      }
    }
  }
}
</script>
<script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
</head>
<body class="bg-dt-bg-root text-dt-text font-sans m-0 p-0 h-screen overflow-hidden">

<div id="admin-app" class="h-screen flex flex-col">
  <!-- 顶栏 -->
  <div class="h-10 bg-dt-bg-root text-dt-text text-sm flex items-center px-4 shrink-0 border-b border-dt-border/30">
    <span class="text-dt-primary-light font-bold">斑图生成器 · 后台管理</span>
    <span class="text-dt-text-muted text-xs ml-4">:8010</span>
    <span class="ml-auto text-xs text-dt-text-muted">{{ lastUpdate }}</span>
  </div>

  <!-- 主体 -->
  <div class="flex flex-1 min-h-0">
    <!-- 左侧导航 -->
    <div class="w-48 bg-dt-bg shrink-0 border-r border-dt-border/30 p-2">
      <button v-for="(page, i) in pages" :key="i"
              @click="activePage = i"
              :class="activePage === i ? 'bg-dt-primary text-white' : 'text-dt-text-secondary hover:bg-dt-bg-hover hover:text-dt-text'"
              class="w-full text-left text-sm py-2 px-3 rounded mb-1 transition-colors">
        {{ page.icon }} {{ page.name }}
      </button>
    </div>

    <!-- 右侧内容 -->
    <div class="flex-1 overflow-y-auto p-4 bg-dt-bg">

      <!-- 页面: Worker池配置 -->
      <div v-show="activePage === 0">
        <h2 class="text-base font-bold text-dt-text mb-4">Worker 池配置</h2>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <!-- 配置表单 -->
          <div class="border border-dt-border rounded p-4">
            <div class="space-y-4">
              <div>
                <label class="text-xs text-dt-text-secondary block mb-1">Worker 数量</label>
                <div class="flex items-center gap-2">
                  <input v-model.number="formWorkerCount" type="range" min="1" max="8" class="flex-1 accent-dt-primary">
                  <span class="text-sm font-bold text-dt-text w-6 text-center">{{ formWorkerCount }}</span>
                </div>
              </div>
              <div>
                <label class="flex items-center gap-2 text-xs text-dt-text-secondary">
                  <input type="checkbox" v-model="formUseGpu" class="accent-dt-primary">
                  使用 GPU 加速
                </label>
              </div>
              <div>
                <label class="text-xs text-dt-text-secondary block mb-1">最大迭代次数限制</label>
                <input v-model.number="formMaxIter" type="number" min="100" max="100000"
                       class="w-32 bg-dt-bg-input border border-dt-border rounded px-2 py-1 text-sm">
              </div>
            </div>
            <button @click="savePoolConfig"
                    class="mt-4 bg-dt-primary text-white text-sm rounded px-4 py-2 hover:bg-dt-primary-light">
              保存配置
            </button>
            <p v-if="saveMessage" class="text-xs mt-2" :class="saveMessageType === 'ok' ? 'text-dt-success' : 'text-dt-danger'">
              {{ saveMessage }}
            </p>
          </div>

          <!-- 当前状态 -->
          <div class="border border-dt-border rounded p-4">
            <h3 class="text-sm font-bold text-dt-text-secondary mb-3">当前运行状态</h3>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-dt-text-muted">Worker 数量</span>
                <span class="text-dt-text font-bold">{{ currentConfig.worker_count }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-dt-text-muted">GPU 加速</span>
                <span :class="currentConfig.use_gpu ? 'text-dt-success' : 'text-dt-text-muted'">
                  {{ currentConfig.use_gpu ? '已启用' : '已禁用' }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-dt-text-muted">最大迭代</span>
                <span class="text-dt-text">{{ currentConfig.max_iterations }}</span>
              </div>
            </div>
            <button @click="restartPool"
                    class="mt-4 bg-dt-warning text-dt-bg-root text-sm rounded px-4 py-2 hover:bg-yellow-400">
              重启 Worker 池
            </button>
          </div>
        </div>
      </div>

      <!-- 页面: 系统监控 -->
      <div v-show="activePage === 1">
        <h2 class="text-base font-bold text-dt-text mb-4">系统监控</h2>

        <!-- 指标卡片 -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div class="border border-dt-border rounded p-3 text-center">
            <div class="text-dt-text-muted text-xs">CPU</div>
            <div class="text-2xl font-bold text-dt-primary">{{ liveData.cpu_percent }}%</div>
          </div>
          <div class="border border-dt-border rounded p-3 text-center">
            <div class="text-dt-text-muted text-xs">GPU</div>
            <div class="text-2xl font-bold text-dt-primary-light">{{ liveData.gpu_percent }}%</div>
          </div>
          <div class="border border-dt-border rounded p-3 text-center">
            <div class="text-dt-text-muted text-xs">内存</div>
            <div class="text-2xl font-bold text-dt-warning">{{ (liveData.system_memory_mb / 1024).toFixed(1) }}GB</div>
          </div>
          <div class="border border-dt-border rounded p-3 text-center">
            <div class="text-dt-text-muted text-xs">队列</div>
            <div class="text-2xl font-bold" :class="liveData.queue_length > 0 ? 'text-dt-danger' : 'text-dt-success'">
              {{ liveData.queue_length }}
            </div>
          </div>
        </div>

        <!-- 折线图 -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          <div class="border border-dt-border rounded p-2">
            <canvas id="chart-cpu" height="160"></canvas>
          </div>
          <div class="border border-dt-border rounded p-2">
            <canvas id="chart-gpu" height="160"></canvas>
          </div>
          <div class="border border-dt-border rounded p-2">
            <canvas id="chart-memory" height="160"></canvas>
          </div>
        </div>

        <!-- Worker 负载 -->
        <div class="border border-dt-border rounded p-3">
          <h3 class="text-xs font-bold text-dt-text-secondary mb-2">Worker 负载</h3>
          <div v-if="liveData.workers && liveData.workers.length" class="flex gap-2">
            <div v-for="w in liveData.workers" :key="w.id"
                 class="flex items-center gap-1 text-xs px-2 py-1 rounded"
                 :class="w.status === 'busy' ? 'bg-dt-primary/20 text-dt-primary-light' : 'bg-dt-bg-input text-dt-text-muted'">
              <span>{{ w.status === 'busy' ? '■' : '□' }}</span>
              Worker {{ w.id }}
              <span v-if="w.job_id" class="ml-1">({{ w.progress }}%)</span>
            </div>
          </div>
          <p v-else class="text-xs text-dt-text-muted">暂无 Worker 信息</p>
        </div>
      </div>

    </div>
  </div>
</div>

<script src="js/admin.js"></script>
</body>
</html>
```

---

### Task 12: 后台管理前端逻辑 — admin.js

**Files:**
- Create: `web/js/admin.js`

- [ ] **Step 1: 编写 admin.js**

```javascript
const { createApp, ref, reactive, onMounted, onUnmounted, nextTick } = Vue;

createApp({
  setup() {
    const activePage = ref(0);
    const pages = [
      { name: 'Worker池配置', icon: '⚙' },
      { name: '系统监控', icon: '📊' },
    ];
    const lastUpdate = ref('');

    // Worker 池配置
    const formWorkerCount = ref(2);
    const formUseGpu = ref(true);
    const formMaxIter = ref(20000);
    const currentConfig = ref({ worker_count: 1, use_gpu: true, max_iterations: 20000 });
    const saveMessage = ref('');
    const saveMessageType = ref('ok');

    // 系统监控实时数据
    const liveData = reactive({
      cpu_percent: 0, cpu_per_core: [],
      gpu_percent: 0, gpu_memory_mb: 0, gpu_memory_total_mb: 8192,
      system_memory_mb: 0, system_memory_total_mb: 16384,
      workers: [], queue_length: 0, timestamp: '',
    });

    // 历史数据
    const historyData = reactive({ timestamps: [], cpu: [], gpu: [], memory_mb: [] });

    // Chart.js 实例
    let chartCPU = null, chartGPU = null, chartMem = null;

    // ── Worker 池配置 ──────────────────────────────
    async function fetchPoolConfig() {
      try {
        const res = await fetch('/api/pool/config');
        const data = await res.json();
        currentConfig.value = data;
        formWorkerCount.value = data.worker_count;
        formUseGpu.value = data.use_gpu;
        formMaxIter.value = data.max_iterations;
      } catch (e) { console.error('获取配置失败:', e); }
    }

    async function savePoolConfig() {
      saveMessage.value = '';
      try {
        const res = await fetch('/api/pool/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            worker_count: formWorkerCount.value,
            use_gpu: formUseGpu.value,
            max_iterations: formMaxIter.value,
          }),
        });
        const data = await res.json();
        currentConfig.value = data.config;
        saveMessage.value = '配置已保存，如需生效请重启 Worker 池。';
        saveMessageType.value = 'ok';
      } catch (e) {
        saveMessage.value = '保存失败: ' + e.message;
        saveMessageType.value = 'error';
      }
    }

    async function restartPool() {
      if (!confirm('确定要重启 Worker 池吗？运行中的任务将中断。')) return;
      try {
        await fetch('/api/pool/restart', { method: 'POST' });
        saveMessage.value = 'Worker 池已重启。';
        saveMessageType.value = 'ok';
      } catch (e) {
        saveMessage.value = '重启失败: ' + e.message;
        saveMessageType.value = 'error';
      }
    }

    // ── WebSocket 监控 ─────────────────────────────
    let ws = null;

    function connectAdminWS() {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${location.host}/ws/system`);
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        Object.assign(liveData, data);
        lastUpdate.value = '更新: ' + (data.timestamp || '');

        // 更新历史数据（保留最近 200 个点）
        historyData.timestamps.push(data.timestamp || '');
        historyData.cpu.push(data.cpu_percent);
        historyData.gpu.push(data.gpu_percent);
        historyData.memory_mb.push(data.system_memory_mb);
        if (historyData.timestamps.length > 200) {
          historyData.timestamps.shift();
          historyData.cpu.shift();
          historyData.gpu.shift();
          historyData.memory_mb.shift();
        }

        updateCharts();
      };
      ws.onclose = () => {
        lastUpdate.value = '连接断开，3秒后重连...';
        setTimeout(connectAdminWS, 3000);
      };
      ws.onerror = () => ws?.close();
    }

    // ── 图表 ────────────────────────────────────────
    function createChart(canvasId, label, color, bgColor) {
      const ctx = document.getElementById(canvasId)?.getContext('2d');
      if (!ctx) return null;
      return new Chart(ctx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [{
            label, data: [], borderColor: color,
            backgroundColor: bgColor || color + '20',
            borderWidth: 2, fill: true, tension: 0.3,
            pointRadius: 0,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          animation: { duration: 300 },
          scales: {
            x: { display: false },
            y: { beginAtZero: true, max: 100,
                 grid: { color: '#1E293B' },
                 ticks: { color: '#64748B', font: { size: 10 } } },
          },
          plugins: {
            legend: { labels: { color: '#94A3B8', font: { size: 10 } } },
          },
        },
      });
    }

    function updateCharts() {
      const len = historyData.timestamps.length;
      if (len < 2) return;

      const labels = historyData.timestamps.slice(-60);
      const cpuData = historyData.cpu.slice(-60);
      const gpuData = historyData.gpu.slice(-60);
      const memData = historyData.memory_mb.slice(-60);

      [chartCPU, chartGPU, chartMem].forEach((ch, i) => {
        if (!ch) return;
        const data = [cpuData, gpuData, memData][i];
        ch.data.labels = labels;
        ch.data.datasets[0].data = data;
        ch.update('none');
      });
    }

    // ── 生命周期 ────────────────────────────────────
    onMounted(async () => {
      await fetchPoolConfig();

      // 等待 DOM 渲染完成
      await nextTick();
      chartCPU = createChart('chart-cpu', 'CPU %', '#3B82F6', '#3B82F620');
      chartGPU = createChart('chart-gpu', 'GPU %', '#60A5FA', '#60A5FA20');
      chartMem = createChart('chart-memory', '内存 MB', '#F59E0B', '#F59E0B20');
      if (chartMem) chartMem.options.scales.y.max = undefined;

      connectAdminWS();
    });

    onUnmounted(() => {
      ws?.close();
      [chartCPU, chartGPU, chartMem].forEach(c => c?.destroy());
    });

    return {
      activePage, pages, lastUpdate,
      formWorkerCount, formUseGpu, formMaxIter,
      currentConfig, saveMessage, saveMessageType,
      liveData,
      fetchPoolConfig, savePoolConfig, restartPool,
    };
  }
}).mount('#admin-app');
```

---

### Task 13: 删除旧入口 — app/main.py 调整

**Files:**
- Modify: `app/main.py`

由于现在用 `start.py` 启动 Web 服务，旧的 tkinter 入口不再使用，但保留作为备用。

- [ ] **Step 1: 在 app/main.py 顶部添加弃用提示**

```python
#!/usr/bin/env python3
"""
斑图生成器 — 应用程序入口 (旧版 tkinter，已废弃)
============================================
请使用项目根目录的 start.py 启动 Web 版本。

旧版保留仅供参考：
    python app/main.py
"""
# ... 后续代码保持不变
```

---

### Task 14: 测试验证

- [ ] **Step 1: 安装依赖**

```bash
cd "D:\斑图生成器"
pip install -r requirements.txt
```

- [ ] **Step 2: 启动服务**

```bash
cd "D:\斑图生成器"
python start.py --host 0.0.0.0
```

- [ ] **Step 3: 验证主站**
  - 浏览器访问 `http://127.0.0.1:8000`
  - 预期：左侧控制面板正常显示，右侧标签页区空
  - 状态栏显示 Workers/队列信息
  - 选择模型、调整参数
  - 点击"运行"提交任务，进度条更新，完成后自动渲染图表

- [ ] **Step 4: 验证后台管理**
  - 浏览器访问 `http://127.0.0.1:8010`
  - 预期：Worker 池配置表单显示当前值
  - 系统监控页面显示 CPU/GPU/内存实时数据
  - 折线图随时间更新

- [ ] **Step 5: 提交代码**

```bash
cd "D:\斑图生成器"
git add -A
git commit -m "feat: HTML 前端改造 — 主站:8000 + 后台:8010"
```
