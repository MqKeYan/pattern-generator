# 斑图生成器 HTML 前端改造设计规范

> **日期**: 2026-07-07  
> **状态**: 已确认  
> **目标**: 将 tkinter 桌面前端替换为 HTML 前端，保留布局设计，前后端完全分离

---

## 1. 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| 后端框架 | FastAPI | REST API + WebSocket 实时状态推送 |
| 前端框架 | Vue 3 (CDN 引入) | 响应式数据绑定、组件化 |
| CSS | Tailwind CSS (CDN 引入) | 深色科学主题、工具类布局 |
| 可视化 | Plotly.js (CDN 引入) | 2D 热力图、3D 曲面、动画 |
| 计算引擎 | PyTorch (保持现有) | GPU/CPU 反应-扩散模拟 |

**无需构建工具**，所有前端依赖通过 CDN 引入，后端通过 `pip install`。

---

## 2. 项目结构

```
斑图生成器/
├── app/                       # 现有 Python 模块 (保持不变)
│   ├── config.py              # 模型配置与常量
│   ├── simulator.py           # PyTorch 模拟引擎
│   ├── models.py              # 反应-扩散方程模型
│   ├── environment.py         # 环境初始化
│   └── ...
├── server/                    # 新增: FastAPI 后端
│   ├── main.py                # 应用入口、API 路由
│   └── websocket.py           # WebSocket 状态推送管理器
├── web/                       # 新增: 前端静态文件
│   ├── index.html             # 主页面 (Vue 3 app)
│   └── js/
│       └── app.js             # Vue 应用逻辑
├── requirements.txt           # 更新: 添加 FastAPI 依赖
└── start.py                   # 新增: 一键启动脚本
```

---

## 3. API 设计

### 3.1 REST 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/models` | 返回所有模型列表及参数定义 |
| GET | `/api/models/{id}` | 返回指定模型的默认参数和推荐值 |
| POST | `/api/simulate` | 提交模拟参数，返回计算结果（2D/3D 数据 + 演化数据） |
| POST | `/api/animate` | 提交动画参数，返回历史帧数据数组 |
| POST | `/api/clean-cache` | 手动清理 GPU/CPU 内存缓存 |

**POST `/api/simulate` 请求体:**

```json
{
  "model": "模型1",
  "params": [0.2, 0.5, 2.0, 0.3, 1.2, 0.05, 0.2],
  "iterations": 9000,
  "init_x_range": [0.95, 1.05],
  "init_y_range": [0.80, 1.0],
  "track_points": [{"x": 25, "y": 50}]
}
```

**POST `/api/simulate` 响应体:**

```json
{
  "x_data": [[...]],           // 2D 数组, 100x100
  "y_data": [[...]],           // 2D 数组, 100x100
  "evolution": {
    "center": {"x": [...], "y": [...]},
    "point_25_50": {"x": [...], "y": [...]}
  },
  "hardware_info": "GPU: NVIDIA GeForce RTX 3060"
}
```

### 3.2 WebSocket

| 路径 | 说明 |
|---|---|
| `/ws/status` | 每 3 秒推送系统状态 |

**推送消息格式:**

```json
{
  "uptime": "01:23:45",
  "cpu_percent": 23.5,
  "gpu_percent": 45.0,
  "memory_mb": 1234.5,
  "gpu_available": true,
  "hardware_info": "GPU: NVIDIA GeForce RTX 3060"
}
```

---

## 4. 前端布局

完全保留现有 tkinter 布局结构：

```
┌──────────────────────────────────────────────────────────┐
│  状态栏: 版本 | 目录 | 启动时间 | 运行时间 | 硬件 | CPU | GPU | 内存  │
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
│ ┌ 控制按钮 ┐ │                                              │
│ └──────────┘ │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

### 4.1 状态栏

- 固定在顶部，高度 `h-8`
- 背景最深色 `bg-[#0B1120]`，文字 `text-[#64748B]`
- 竖线分隔各段 (`|`)
- 通过 WebSocket 每 3 秒更新运行时间、CPU、GPU、内存数据
- 版本号、目录、启动时间、硬件信息为静态文本

### 4.2 左侧控制面板

- 固定宽度 `w-72` (288px)
- 滚动区域，高度撑满
- 包含 6 张卡片，按现有顺序排列：

| 卡片 | 内容 |
|---|---|
| 模型设置 | 模型下拉框 (Combobox) + 迭代次数输入 + 动画帧数输入 |
| 参数设置 | 8 个参数行 (标签 + 输入框 + 重置按钮)，随模型切换动态变化 |
| 初始值范围 | X min/max + Y min/max 四个输入框 + 重置按钮 + "应用最佳初始值" |
| 跟踪点 | X/Y 坐标输入 + "添加"按钮 + "清空"按钮 + 已添加点列表 |
| 缓存管理 | 自动清理复选框 + "清理缓存"按钮 + 清理次数/时间/状态 |
| 控制按钮 | "运行" "重置" "播放" "暂停" 四个按钮 |

### 4.3 右侧标签页

- 三个标签页，使用 Tailwind + Vue 实现标签切换
- 标签选中态：蓝色背景 `bg-[#3B82F6]`，未选中：灰色 `bg-[#1E293B]`

**二维斑图标签页:**
- Plotly.js heatmap: X种群 (viridis), Y种群 (plasma), 合并斑图 (RGB叠加)
- 底部时间演化曲线 (Plotly.js line chart)，图例可点击切换可见性

**三维斑图标签页:**
- Plotly.js 3D surface plot: X种群曲面

**动画演示标签页:**
- Plotly.js 动画 heatmap: 并排 X种群 + Y种群 + 时间演化曲线
- 播放/暂停控制

---

## 5. 颜色主题

将 `theme.py` 中的设计令牌映射为 Tailwind CSS 自定义颜色：

```javascript
// tailwind config (内联)
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

## 6. Vue 3 组件划分

所有代码放在 `app.js` 中，以 Vue 3 Options API 组织（便于 CDN 环境理解）：

- **数据状态**: model, params, iterations, frames, xRange, yRange, trackPoints, autoClean, simResult, isSimulating, statusData
- **计算属性**: currentModelConfig, isAnimating
- **方法**: 
  - `fetchModels()` — 加载模型列表
  - `onModelChange()` — 切换模型时更新参数面板
  - `runSimulation()` — POST 提交模拟
  - `startAnimation()` — POST 提交动画数据
  - `pauseAnimation()` — Plotly 动画控制
  - `addTrackPoint()` / `clearTrackPoints()` — 跟踪点管理
  - `cleanCache()` — POST 清理缓存
  - `resetAll()` — 重置所有设置
  - `render2D()` / `render3D()` / `renderAnim()` — Plotly 图表渲染
- **生命周期**: `mounted()` 时获取模型列表、建立 WebSocket 连接

---

## 7. 启动方式

`start.py` 一键启动：

```python
import uvicorn
import webbrowser
import threading

def open_browser():
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    threading.Timer(1.5, open_browser).start()
    uvicorn.run("server.main:app", host="127.0.0.1", port=8000)
```

---

## 8. 不涉及改动

- `app/simulator.py` — 模拟引擎保持不变
- `app/models.py` — 模型方程保持不变
- `app/config.py` — 配置常量保持不变（后端和前端各自引用）
- `app/theme.py` — 不再需要，配色由 Tailwind 实现
- `app/ui_widgets.py` — 不再需要，UI 由 Vue 实现
- `app/app_window.py` — 不再需要，业务逻辑迁移至 server/
- `app/visualizer.py` — 不再需要，可视化由 Plotly.js 实现
- `app/environment.py` — 部分保留（字体配置不再需要）

---

## 9. 依赖变更

`requirements.txt` 新增：
```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
```

移除（不再直接依赖）：
```
matplotlib  # 前端用 Plotly.js 替代
```

保留：
```
torch, numpy, psutil  # 模拟引擎和系统监控仍需要
```
