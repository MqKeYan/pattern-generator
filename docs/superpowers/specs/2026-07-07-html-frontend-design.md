# 斑图生成器 HTML 前端改造设计规范

> **日期**: 2026-07-07  
> **状态**: 已确认  
> **目标**: 将 tkinter 桌面前端替换为 HTML 前端，保留布局设计，仅局域网使用  
> **架构**: 主站 `:8000` + 后台管理 `:8001`，不同端口，共享后端

---

## 1. 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| 后端框架 | FastAPI | REST API + WebSocket 实时推送 |
| 前端框架 | Vue 3 (CDN 引入) | 响应式数据绑定、组件化 |
| CSS | Tailwind CSS (CDN 引入) | 深色科学主题、工具类布局 |
| 可视化 (主站) | Plotly.js (CDN 引入) | 2D 热力图、3D 曲面、动画 |
| 可视化 (后台) | Chart.js (CDN 引入) | CPU/GPU/内存时序折线图 |
| 进程管理 | Python multiprocessing | Worker 进程池 |
| 计算引擎 | PyTorch (保持现有) | GPU/CPU 反应-扩散模拟 |

**无需构建工具**，所有前端依赖通过 CDN 引入，后端通过 `pip install`。  
**无需外部中间件**，任务队列和结果存储均基于本地文件 + 内存。

---

## 2. 架构概览

```
局域网设备
    │
    ├─ http://<服务器IP>:8000  → 主站 (斑图生成器工作台，所有人使用)
    │
    └─ http://<服务器IP>:8001  → 后台管理 (性能配置 + 监控，管理员使用)

                    │                    │
                    ▼                    ▼
          ┌─────────────────────────────────────┐
          │            FastAPI 进程              │
          │  ┌───────┐  ┌──────┐  ┌─────────┐  │
          │  │主站路由│  │后台路由│  │WebSocket│  │
          │  └───────┘  └──────┘  └─────────┘  │
          │          │           │              │
          │          ▼           ▼              │
          │  ┌───────────┐  ┌───────────────┐   │
          │  │ Worker池  │  │ 系统监控采集   │   │
          │  │(PyTorch)  │  │(psutil/gpu)   │   │
          │  └───────────┘  └───────────────┘   │
          │         │                            │
          │         ▼                            │
          │  ┌───────────┐                       │
          │  │ 结果存储   │                       │
          │  │(内存+文件) │                       │
          │  └───────────┘                       │
          └─────────────────────────────────────┘
```

### 端口划分

| 端口 | 路径 | 用途 | 访问者 |
|---|---|---|---|
| 8000 | `/` | 主站静态页面 (斑图生成器工作台) | 所有用户 |
| 8000 | `/api/` | 主站业务 API (模拟、任务) | 所有用户 |
| 8000 | `/ws/` | 主站 WebSocket (状态、任务通知) | 所有用户 |
| 8001 | `/` | 后台管理静态页面 | 管理员 |
| 8001 | `/api/` | 后台管理 API (池配置、系统监控) | 管理员 |
| 8001 | `/ws/` | 后台 WebSocket (高频系统监控) | 管理员 |

两个端口共享同一个 Python 进程内的 Worker 池和任务队列，`start.py` 一次性启动两个 uvicorn 实例。

### 会话机制

- 首次访问自动生成 `session_id`（UUID），存储在浏览器 localStorage
- 无需登录，session_id 用于区分用户和追踪任务
- 页面刷新后 session_id 保持不变，仍可查看历史任务

### 资源池

- 启动时创建 N 个 worker 子进程，N 默认为 GPU 数量（或 CPU 核心数）
- 每个 worker 独立加载 PyTorch 模型，持有专属 GPU 上下文
- 主进程维护任务队列，空闲 worker 自动拉取新任务
- 后台管理可动态调整 worker 数量和计算模式

---

## 3. 项目结构

```
斑图生成器/
├── app/                       # 现有 Python 模块 (保持不变)
│   ├── config.py              # 模型配置与常量
│   ├── simulator.py           # PyTorch 模拟引擎
│   ├── models.py              # 反应-扩散方程模型
│   └── environment.py         # 环境初始化(部分保留)
├── server/                    # 新增: FastAPI 后端
│   ├── main.py                # 主站 FastAPI 应用 + 路由
│   ├── admin_app.py           # 后台管理 FastAPI 应用 + 路由
│   ├── pool.py                # Worker 进程池管理 (两个 app 共享)
│   ├── worker.py              # 子进程入口: 接收任务→执行→返回结果
│   ├── collector.py           # 系统监控数据采集 (CPU/GPU/内存)
│   └── store.py               # 结果存储(TTL缓存 + 文件)
├── web/                       # 新增: 前端静态文件
│   ├── index.html             # 主站页面 (Vue 3 + Tailwind + Plotly)
│   ├── admin.html             # 后台管理页面 (Vue 3 + Tailwind + Chart.js)
│   └── js/
│       ├── app.js             # 主站 Vue 应用逻辑
│       └── admin.js           # 后台管理 Vue 应用逻辑
├── requirements.txt           # 更新: 添加 FastAPI
└── start.py                   # 新增: 一键启动 (双端口)
```

---

## 4. API 设计

### 4.1 主站 REST 接口 (端口 8000)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/session` | 返回或创建 session_id |
| GET | `/api/models` | 返回所有模型列表及参数定义 |
| GET | `/api/models/{id}` | 返回指定模型的默认参数和推荐值 |
| POST | `/api/jobs` | 提交模拟/动画任务，立即返回 job_id |
| GET | `/api/jobs` | 当前 session 的所有任务列表及状态 |
| GET | `/api/jobs/{job_id}` | 任务状态 + (如已完成)结果数据 |
| DELETE | `/api/jobs/{job_id}` | 取消排队中的任务或删除已完成任务 |

### 4.2 后台管理 REST 接口 (端口 8001)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/pool/config` | 获取当前 Worker 池配置 |
| PUT | `/api/pool/config` | 更新 Worker 数量、计算模式 (GPU/CPU) |
| POST | `/api/pool/restart` | 重启 Worker 池 (应用新配置) |
| GET | `/api/pool/workers` | 各 Worker 状态: idle/busy + 当前任务 |
| GET | `/api/system/current` | 当前 CPU/GPU/内存瞬时值 |
| GET | `/api/system/history?minutes=10` | 近 N 分钟 CPU/GPU/内存历史数据 |

**PUT `/api/pool/config` 请求体:**

```json
{
  "worker_count": 4,
  "use_gpu": true,
  "max_iterations": 20000
}
```

**GET `/api/system/history` 响应:**

```json
{
  "timestamps": ["10:30:00", "10:30:05", ...],
  "cpu": [23.5, 25.1, ...],
  "gpu": [45.0, 44.8, ...],
  "memory_mb": [1234, 1236, ...]
}
```

### 4.3 任务生命周期 (主站)

```
POST /api/jobs  →  状态: queued  →  worker领取  →  状态: running  →  完成  →  状态: completed
                       │                              │                    │
                       └── 可取消(DELETE)              └── 可取消           └── 结果TTL=1小时
```

**POST `/api/jobs` 请求体:**

```json
{
  "session_id": "uuid-string",
  "job_type": "simulate",
  "model": "模型1",
  "params": [0.2, 0.5, 2.0, 0.3, 1.2, 0.05, 0.2],
  "iterations": 9000,
  "init_x_range": [0.95, 1.05],
  "init_y_range": [0.80, 1.0],
  "track_points": [{"x": 25, "y": 50}]
}
```

**响应:** `{"job_id": "uuid", "status": "queued", "position": 2}`

**GET `/api/jobs/{job_id}` 响应 (运行中):**

```json
{
  "job_id": "uuid",
  "status": "running",
  "progress": 45,
  "created_at": "2026-07-07T10:30:00"
}
```

**GET `/api/jobs/{job_id}` 响应 (已完成):**

```json
{
  "job_id": "uuid",
  "status": "completed",
  "progress": 100,
  "created_at": "2026-07-07T10:30:00",
  "completed_at": "2026-07-07T10:32:15",
  "result": {
    "hardware_info": "GPU: NVIDIA GeForce RTX 3060",
    "x_data": [[...]],
    "y_data": [[...]],
    "evolution": {
      "center": {"x": [...], "y": [...]},
      "point_25_50": {"x": [...], "y": [...]}
    }
  }
}
```

### 4.4 WebSocket

**主站 (端口 8000):**

| 路径 | 说明 |
|---|---|
| `/ws/status` | 每 3 秒推送简易系统状态 |
| `/ws/jobs/{session_id}` | 该 session 的任务状态变更推送 |

**后台管理 (端口 8001):**

| 路径 | 说明 |
|---|---|
| `/ws/system` | 每 1 秒推送完整系统监控数据 (CPU/GPU/内存/Worker负载) |

**`/ws/status` 推送格式 (主站):**

```json
{
  "uptime": "01:23:45",
  "cpu_percent": 23.5,
  "gpu_percent": 45.0,
  "memory_mb": 1234.5,
  "workers_total": 4,
  "workers_busy": 2,
  "queue_length": 3
}
```

**`/ws/system` 推送格式 (后台):**

```json
{
  "timestamp": "10:30:05",
  "cpu_percent": 23.5,
  "cpu_per_core": [30.1, 18.2, 25.0, 20.7],
  "gpu_percent": 45.0,
  "gpu_memory_mb": 2048,
  "gpu_memory_total_mb": 8192,
  "system_memory_mb": 1234,
  "system_memory_total_mb": 16384,
  "workers": [
    {"id": 0, "status": "busy", "job_id": "abc", "progress": 65},
    {"id": 1, "status": "busy", "job_id": "def", "progress": 30},
    {"id": 2, "status": "idle", "job_id": null, "progress": null},
    {"id": 3, "status": "idle", "job_id": null, "progress": null}
  ],
  "queue_length": 3
}
```

---

## 5. 进程池设计

### 5.1 主进程

- 管理 FastAPI 应用 (两个端口共享)
- 维护 job 队列 (asyncio.Queue)
- 维护 worker 进程列表
- 通过 `multiprocessing.Pipe` 与每个 worker 通信
- 接收 worker 结果，写入 store
- 运行系统监控采集器 (collector.py)，每 1 秒收集 CPU/GPU/内存数据

### 5.2 Worker 进程 (worker.py)

```python
def worker_loop(pipe, device_id):
    # 每个 worker 绑定一块 GPU (如有)
    simulator = PatternSimulator(grid_size=100, use_cuda=True)
    
    while True:
        job = pipe.recv()          # 阻塞等待任务
        if job is None:            # 关闭信号
            break
        result = simulator.simulate(...)  # 执行模拟
        pipe.send({"job_id": job.id, "result": result})
```

### 5.3 Worker 数量

| 硬件 | 默认 worker 数 |
|---|---|
| 有 GPU | GPU 数量 (每 GPU 一个 worker，独占显存) |
| 纯 CPU | CPU 逻辑核心数 - 1 (至少 1) |
| 后台动态调整 | 通过 PUT `/api/pool/config` 修改，需重启池生效 |

### 5.4 结果存储 (store.py)

- 小结果 (< 10MB): 内存 dict，TTL 1 小时后自动清除
- 大结果 (≥ 10MB): 写入临时文件 `temp/results/{job_id}.npz`，TTL 同上
- 后台定时任务每分钟清理过期结果
- 每个 session 最多保留 20 个任务记录

---

## 6. 前端布局

### 6.1 主站 (端口 8000)

完全保留现有 tkinter 布局结构：

```
┌──────────────────────────────────────────────────────────┐
│  状态栏: 版本 | 启动时间 | 运行时间 | 硬件 | CPU | GPU | 内存   │
│         Workers: 2/4 忙 | 队列: 3                        │
├──────────────┬───────────────────────────────────────────┤
│ 左侧面板      │  右侧标签页区                              │
│ (w-72,       │                                           │
│  滚动)       │  ┌─ 二维斑图 ─┬─ 三维斑图 ─┬─ 动画演示 ──┐  │
│              │  │                                        │  │
│ ┌ 模型设置 ┐ │  │     Plotly.js 图表渲染区                  │  │
│ └──────────┘ │  │                                        │  │
│ ┌ 参数设置 ┐ │  ├────────────────────────────────────────┤  │
│ └──────────┘ │  │  时间演化曲线 (仅二维标签页底部显示)       │  │
│ ┌ 初始范围 ┐ │  │                                        │  │
│ └──────────┘ │  └────────────────────────────────────────┘  │
│ ┌ 跟踪点  ┐ │                                              │
│ └──────────┘ │                                              │
│ ┌ 控制按钮 ┐ │                                              │
│ ┌ 任务状态 ┐ │  进度条 + 状态文字 + 历史列表                 │
│ └──────────┘ │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

**左侧面板从 6 张卡片调整为 6 张：**

| 卡片 | 内容 |
|---|---|
| 模型设置 | 模型下拉框 + 迭代次数 + 动画帧数 |
| 参数设置 | 8 个参数行 (标签+输入+重置)，随模型切换动态变化 |
| 初始值范围 | X min/max + Y min/max + 重置 + "应用最佳值"按钮 |
| 跟踪点 | X/Y 输入 + 添加/清空 + 已添加点列表 |
| 控制按钮 | 运行 / 重置 / 播放 / 暂停 |
| 任务状态 | 进度条 + 状态文字 + 最近 5 个任务历史 |

**右侧标签页:**

- **二维斑图**: Plotly.js 三列热力图 (X种群/Y种群/合并) + 底部演化曲线
- **三维斑图**: Plotly.js 3D 曲面图
- **动画演示**: Plotly.js 动画热力图 + 播放/暂停

### 6.2 后台管理 (端口 8001)

```
┌──────────────────────────────────────────────────────────┐
│  后台管理 — 斑图生成器                            [8001]  │
├──────────────────────┬───────────────────────────────────┤
│  导航                │                                   │
│  ◉ Worker池配置      │  实时系统监控                       │
│  ○ 系统监控          │                                   │
│                      │  ┌──────┐ ┌──────┐ ┌──────┐ ┌───┐│
│                      │  │ CPU  │ │ GPU  │ │ 内存  │ │队列││
│                      │  │ 23%  │ │ 45%  │ │1.2GB │ │ 3 ││
│                      │  └──────┘ └──────┘ └──────┘ └───┘│
│                      │                                   │
│                      │  CPU 使用率 (Chart.js 折线图)       │
│                      │  ▂▃▅▃▂▁▂▃▆▇▅▃▂▁▂▃▅▇█▅▃▂         │
│                      │                                   │
│                      │  GPU 使用率 (Chart.js 折线图)       │
│                      │  ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁▂▃▄▅▆▇█▇▆       │
│                      │                                   │
│                      │  内存使用 (Chart.js 折线图)         │
│                      │  ▃▃▃▄▄▅▅▆▆▆▆▆▆▆▆▆▅▅▄▄▃▃▃       │
│                      │                                   │
│                      │  Worker 负载状态                   │
│                      │  [■ busy] [■ busy] [□ idle] [□ idle]│
│                      │  任务1:65%   任务2:30%             │
│                      └───────────────────────────────────┘
└──────────────────────────────────────────────────────────┘
```

**后台管理左侧导航:**

| 页面 | 内容 |
|---|---|
| Worker池配置 | Worker 数量滑块(1-8) + GPU/CPU 开关 + 最大迭代数限制 + 当前配置展示 + 重启按钮 |
| 系统监控 | 4 个指标卡片 (CPU/GPU/内存/队列长度) + 3 个实时折线图 + Worker 负载状态列表 |

---

## 7. 颜色主题

两个站点共用同一套深色科学主题，将 `theme.py` 中的设计令牌映射为 Tailwind CSS 自定义颜色：

```javascript
tailwind.config = {
  theme: {
    extend: {
      colors: {
        'dt-bg-root': '#0B1120',
        'dt-bg': '#0F172A',
        'dt-bg-elevated': '#1E293B',
        'dt-bg-input': '#1A2332',
        'dt-bg-hover': '#334155',
        'dt-border': '#1E3A5F',
        'dt-border-focus': '#3B82F6',
        'dt-text': '#F1F5F9',
        'dt-text-secondary': '#94A3B8',
        'dt-text-muted': '#64748B',
        'dt-primary': '#3B82F6',
        'dt-primary-light': '#60A5FA',
        'dt-success': '#22C55E',
        'dt-danger': '#EF4444',
        'dt-warning': '#F59E0B',
      }
    }
  }
}
```

---

## 8. 前端数据流

### 8.1 主站 (app.js)

```
sessionId         — 会话 ID (localStorage 持久化)
models            — 模型列表 (启动时获取)
currentModel      — 当前选中模型
params            — 8 个参数值数组
iterations        — 迭代次数
frames            — 动画帧数
xRange, yRange    — 初始值范围
trackPoints       — 跟踪点列表

// 异步任务
currentJobId      — 当前运行/等待的任务 ID
jobStatus         — null | 'queued' | 'running' | 'completed'
jobProgress       — 0-100
jobPosition       — 队列位置
jobResult         — 完成后的结果数据
jobHistory        — [{job_id, status, model, time}]

// 系统状态 (WebSocket)
uptime, cpu, gpu, memory, workersBusy, workersTotal, queueLength
```

### 8.2 后台管理 (admin.js)

```
// Worker池配置
workerCount       — 当前 worker 数量
useGpu            — 是否使用 GPU
maxIterations     — 最大迭代次数限制
poolConfigDirty   — 配置是否已修改待重启

// 系统监控 (WebSocket 每秒)
cpuPercent        — CPU 总使用率
cpuPerCore        — 每核心使用率数组
gpuPercent        — GPU 使用率
gpuMemory         — GPU 显存使用/总量
sysMemory         — 系统内存使用/总量
workers           — [{id, status, job_id, progress}]
queueLength       — 排队任务数

// 历史数据 (用于折线图)
cpuHistory        — 最近 10 分钟 CPU 历史点
gpuHistory        — 最近 10 分钟 GPU 历史点
memoryHistory     — 最近 10 分钟内存历史点
```

### 8.3 任务提交流程 (主站)

```
用户点"运行" → submitJob("simulate") → 显示进度条 → 轮询job状态
                                               ↓
                    完成后自动渲染 → 2D标签页显示热力图 + 演化曲线
                                   → 3D标签页显示曲面图
```

---

## 9. 部署与启动

### 9.1 启动方式

```bash
# 默认: 主站 8000, 后台 8001, 仅本机访问
python start.py

# 局域网部署: 同一网段设备均可访问
python start.py --host 0.0.0.0

# 自定义端口
python start.py --host 0.0.0.0 --port 8000 --admin-port 8001

# 不自动打开浏览器
python start.py --host 0.0.0.0 --no-browser
```

局域网用户访问 `http://<服务器IP>:8000`，管理员访问 `http://<服务器IP>:8001`。

### 9.2 start.py

```python
import uvicorn
import webbrowser
import argparse
import threading
import asyncio

def run_server(app, host, port):
    """在独立线程中运行 uvicorn"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="斑图生成器 Web 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--admin-port", type=int, default=8001)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    from server.main import app
    from server.admin_app import admin_app

    # 后台管理独立线程
    threading.Thread(
        target=run_server, args=(admin_app, args.host, args.admin_port),
        daemon=True
    ).start()

    # 自动打开浏览器
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(
            f"http://{args.host}:{args.port}")).start()

    # 主站在主线程运行
    uvicorn.run(app, host=args.host, port=args.port)
```

---

## 10. 不涉及改动

- `app/simulator.py` — 模拟引擎保持不变
- `app/models.py` — 模型方程保持不变
- `app/config.py` — 配置常量保持不变
- `app/theme.py` — 不再需要，配色由 Tailwind 实现
- `app/ui_widgets.py` — 不再需要，UI 由 Vue 实现
- `app/app_window.py` — 不再需要，业务逻辑迁移至 server/
- `app/visualizer.py` — 不再需要，可视化由 Plotly.js 实现
- `app/environment.py` — 部分保留（字体配置不再需要）

---

## 11. 依赖变更

`requirements.txt` 新增：
```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
aiofiles>=23.0.0
```

移除（不再直接依赖）：
```
matplotlib  # 前端用 Plotly.js 替代
```

保留：
```
torch, numpy, psutil  # 模拟引擎和系统监控仍需要
```
