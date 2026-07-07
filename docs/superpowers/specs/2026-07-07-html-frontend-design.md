# 斑图生成器 HTML 前端改造设计规范

> **日期**: 2026-07-07  
> **状态**: 已确认  
> **目标**: 将 tkinter 桌面前端替换为 HTML 前端，保留布局设计，支持局域网和公网多人同时使用

---

## 1. 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| 后端框架 | FastAPI | REST API + WebSocket 实时推送 |
| 前端框架 | Vue 3 (CDN 引入) | 响应式数据绑定、组件化 |
| CSS | Tailwind CSS (CDN 引入) | 深色科学主题、工具类布局 |
| 可视化 | Plotly.js (CDN 引入) | 2D 热力图、3D 曲面、动画 |
| 进程管理 | Python multiprocessing | Worker 进程池 |
| 计算引擎 | PyTorch (保持现有) | GPU/CPU 反应-扩散模拟 |

**无需构建工具**，所有前端依赖通过 CDN 引入，后端通过 `pip install`。  
**无需外部中间件**，任务队列和结果存储均基于本地文件 + 内存。

---

## 2. 架构概览

```
浏览器-1 ─┐
浏览器-2 ─┼── HTTP/WS ──→ FastAPI 主进程 ──→ Worker 进程池 ──→ PyTorch/GPU
浏览器-N ─┘                    │                    │
                         内存任务队列         子进程独立计算
                         结果缓存(TTL)       各自持有 GPU 上下文
                           文件存储
```

### 会话机制

- 首次访问自动生成 `session_id`（UUID），存储在浏览器 localStorage
- 无需登录，session_id 用于区分用户和追踪任务
- 页面刷新后 session_id 保持不变，仍可查看历史任务

### 资源池

- 启动时创建 N 个 worker 子进程，N 默认为 GPU 数量（或 CPU 核心数）
- 每个 worker 独立加载 PyTorch 模型，持有专属 GPU 上下文
- 主进程维护任务队列，空闲 worker 自动拉取新任务
- 环境变量 `WORKER_COUNT` 可覆盖 worker 数量

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
│   ├── main.py                # 应用入口 + API 路由
│   ├── pool.py                # Worker 进程池管理
│   ├── worker.py              # 子进程入口: 接收任务→执行→返回结果
│   └── store.py               # 结果存储(TTL缓存 + 文件)
├── web/                       # 新增: 前端静态文件
│   ├── index.html             # 主页面 (Vue 3 + Tailwind + Plotly)
│   └── js/
│       └── app.js             # Vue 应用逻辑
├── requirements.txt           # 更新: 添加 FastAPI
└── start.py                   # 新增: 一键启动脚本
```

---

## 4. API 设计

### 4.1 REST 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/session` | 返回或创建 session_id |
| GET | `/api/models` | 返回所有模型列表及参数定义 |
| GET | `/api/models/{id}` | 返回指定模型的默认参数和推荐值 |
| POST | `/api/jobs` | 提交模拟/动画任务，立即返回 job_id |
| GET | `/api/jobs` | 当前 session 的所有任务列表及状态 |
| GET | `/api/jobs/{job_id}` | 任务状态 + (如已完成)结果数据 |
| DELETE | `/api/jobs/{job_id}` | 取消排队中的任务或删除已完成任务 |
| GET | `/api/pool/status` | 资源池状态: worker 数、忙/闲、队列长度 |

### 4.2 任务生命周期

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

### 4.3 WebSocket

| 路径 | 说明 |
|---|---|
| `/ws/status` | 每 3 秒推送服务器系统状态 |
| `/ws/jobs/{session_id}` | 该 session 的任务状态变更推送 |

**`/ws/status` 推送格式:**

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

**`/ws/jobs/{session_id}` 推送格式:**

```json
{
  "job_id": "uuid",
  "status": "completed",
  "progress": 100
}
```

---

## 5. 进程池设计

### 5.1 主进程 (main.py)

- 管理 FastAPI 应用
- 维护 job 队列 (asyncio.Queue)
- 维护 worker 进程列表
- 通过 `multiprocessing.Pipe` 与每个 worker 通信
- 接收 worker 结果，写入 store

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
| 环境变量覆盖 | `WORKER_COUNT=4` |

### 5.4 结果存储 (store.py)

- 小结果 (< 10MB): 内存 dict，TTL 1 小时后自动清除
- 大结果 (≥ 10MB): 写入临时文件 `temp/results/{job_id}.npz`，TTL 同上
- 后台定时任务每分钟清理过期结果
- 每个 session 最多保留 20 个任务记录

---

## 6. 前端布局

完全保留现有 tkinter 布局结构：

```
┌──────────────────────────────────────────────────────────┐
│  状态栏: 版本 | 目录 | 启动时间 | 运行时间 | 硬件 | CPU | GPU | 内存 │
│         + Workers: 2/4 忙 | 队列: 3                      │
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
│ ┌ 缓存管理 ┐ │                                              │
│ └──────────┘ │                                              │
│ ┌ 控制按钮 ┐ │  运行/重置/播放/暂停                          │
│ ┌ 任务队列 ┐ │  当前任务状态 + 进度条 (新增)                  │
│ └──────────┘ │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

### 6.1 新增: 任务状态卡片

由于异步执行，左侧面板新增一个卡片显示当前 session 的任务状态：

| 元素 | 说明 |
|---|---|
| 进度条 | 当前运行任务的进度百分比 |
| 状态文字 | "排队中 (第2位)" / "运行中 45%" / "已完成" / "已取消" |
| 任务历史列表 | 最近 5 个任务的状态 (已完成/已取消) |

### 6.2 状态栏扩展

在原有基础上增加池状态信息：
- `Workers: 2/4 忙` — 当前忙碌 worker / 总 worker
- `队列: 3` — 排队中的任务数

---

## 7. 颜色主题

将 `theme.py` 中的设计令牌映射为 Tailwind CSS 自定义颜色：

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

## 8. Vue 3 数据流

### 8.1 状态数据

```
sessionId         — 会话 ID (localStorage 持久化)
models            — 模型列表 (启动时获取)
currentModel      — 当前选中模型
params            — 8 个参数值数组
iterations        — 迭代次数
frames            — 动画帧数
xRange, yRange    — 初始值范围
trackPoints       — 跟踪点列表
autoClean         — 自动清理开关

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

### 8.2 核心方法

```
fetchModels()             — GET /api/models
onModelChange()           — 切换模型，更新参数/初始值面板
submitJob(type)           — POST /api/jobs，返回 job_id
pollJobStatus()           — GET /api/jobs/{id}，轮询直到完成
cancelJob()               — DELETE /api/jobs/{id}
render2D/3D/Anim()        — Plotly.js 渲染
fetchJobHistory()         — GET /api/jobs，恢复历史

onJobComplete()           — 任务完成回调，自动渲染图表到对应标签页
```

### 8.3 任务提交流程

```
用户点"运行" → submitJob("simulate") → 显示进度条 → 轮询job状态
                                               ↓
                    完成后自动渲染 → 2D标签页显示热力图 + 演化曲线
                                   → 3D标签页显示曲面图
```

---

## 9. 部署与启动

### 9.1 局域网部署

```bash
# 直接启动，绑定 0.0.0.0 以便局域网访问
python start.py --host 0.0.0.0 --port 8000
# 局域网其他设备访问: http://<服务器IP>:8000
```

### 9.2 公网部署

```bash
# 方案A: 直接暴露 (测试用)
python start.py --host 0.0.0.0 --port 80

# 方案B: Nginx 反向代理 (推荐)
# nginx 配置示例:
#   location / { proxy_pass http://127.0.0.1:8000; }
#   location /ws/ { proxy_pass http://127.0.0.1:8000;
#                    proxy_http_version 1.1;
#                    proxy_set_header Upgrade $http_upgrade;
#                    proxy_set_header Connection "upgrade"; }
```

### 9.3 start.py

```python
import uvicorn
import webbrowser
import argparse
import threading

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(
            f"http://{args.host}:{args.port}")).start()

    uvicorn.run("server.main:app", host=args.host, port=args.port)
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
