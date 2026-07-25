<h1 align="center">
  <br>
  <strong>🦋 斑图生成器——反应扩散方程可视化工具</strong>
  <br>
</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/Release-v1.3.1-brightgreen"></a>
  <a href="#"><img src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20x64-lightgrey"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/PyTorch-2.0+-EE4C2C?logo=pytorch&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/Vue-3.x-4FC08D?logo=vuedotjs&logoColor=white"></a>
</p>

<p align="center">
  <strong> 5 种捕食者-猎物反应扩散模型，GPU 加速模拟，实时可视化螺旋波、斑点、条纹等斑图形成过程 </strong>
</p>

## 功能概览

| 功能 | 说明 |
|------|------|
| ⚡ GPU 加速 | PyTorch CUDA 后端，比纯 CPU 快 |
| 🖼️ 多维可视化 | Plotly.js 二维热力图 / 三维曲面 / 时序动画，自定义跟踪点 |
| 🎛️ 参数调优 | 7-8 个参数滑块调节，实时切换模型，一键重置默认值 |
| 🖥️ 双端口 Web 服务 | 主站 :8000 提交模拟 + 后台管理 :8010 监控系统 |
| 👥 多用户支持 | Worker 进程池隔离，LAN 内多人同时提交任务 |
| 📊 系统监控 | CPU / GPU 温度与占用、内存、磁盘、Worker 负载、任务统计 |
| 🔧 Worker 池管理 | 后台页面配置 Worker 数量、GPU 开关、最大迭代数，支持热重启 |
| 🌐 LAN 部署 | start.py 一键启动双端口服务，局域网任意设备浏览器访问 |

## 模型与斑图

| 模型 | 典型斑图 | 参数数量 | 推荐迭代 |
|------|---------|---------|---------|
| 模型1 · Rosenzweig-MacArthur | 螺旋波、斑点斑图 | 7 | 9,000 |
| 模型2 · Holling II | 条纹斑图、迷宫斑图 | 8 | 15,000 |
| 模型3 · Ratio-dependent | 螺旋波、靶波 | 8 | 15,000 |
| 模型4 · 对称竞争 | 斑点斑图、相分离斑图 | 3 | 10,000 |
| 模型5 · 连续化离散 | 复杂动态斑图、混沌斑图 | 8 | 4,000 |

## 系统要求

| 项目 | 最低要求 |
|------|---------|
| 操作系统 | Windows 10 版本 1809 及以上 / Windows 11 |
| 架构 | 64 位（x64） |
| 内存 | 建议 8GB 及以上 |
| GPU（可选） | NVIDIA GPU + CUDA 12.x，显存 4GB+ |
| 浏览器 | Edge / Chrome / Firefox（访问 Web 界面） |

## 快速开始

### 下载 & 运行

1. 从 [Releases](../../releases) 页面下载最新版 `.7z` 压缩包
2. 解压到任意目录（**不要放在需要管理员权限的目录**，如 `C:\Program Files`）
3. 注意解压后的 `pattern-generator.exe` 需要和 `_internal/` 文件夹在同一目录
4. 额外安装 `Pytorch` 依赖，支持 `CUDA 13.2` 版本的下载指令 `pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu132`，或者前往[官网](https://pytorch.org/get-started/locally/)
5. 双击运行 `pattern-generator.exe`，浏览器自动打开主站页面

### 从源码运行

```bash
# 环境要求：Python 3.13+
git clone https://github.com/MqKeYan/pattern-generator.git
cd pattern-generator
pip install -r requirements.txt

# GPU 加速（CUDA 13.2+）
nvidia-smi #查看 CUDA 版本信息
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132

# 启动服务
python start.py --host 0.0.0.0
```

启动后：
- 主站：http://localhost:8000
- 后台：http://localhost:8010

### 打包为 exe

```bash
pip install pyinstaller>=6.0
pyinstaller pattern-generator.spec
```

打包产物在 `dist/pattern-generator/` 目录。

## 使用流程

1. **选择模型**：首页下拉选择 5 种模型之一，参数面板自动加载默认值
2. **调整参数**：拖动滑块或直接输入参数值，点击参数名旁的 ↺ 按钮重置单个参数
3. **设置跟踪点**（可选）：输入网格坐标 (0-99)，添加自定义跟踪点观察时间演化
4. **启动模拟**：调整迭代次数，点击「开始模拟」，实时查看进度
5. **查看结果**：二维热力图（X种群 / Y种群 / 合并斑图）+ 中心点演化曲线
6. **管理后台**：打开 :8010 端口，配置 Worker 池、监控系统资源、查看任务队列

## 项目结构

```
app/                                 # 正式软件代码
├── __init__.py                      # 版本号
│
├── engine/                          # 计算引擎
│   ├── config.py                    # 模型参数配置 — 参数名、默认值、初始范围、含义
│   ├── models.py                    # 5 种反应扩散方程实现 + 拉普拉斯算子
│   └── simulator.py                 # 模拟引擎 — 网格初始化、迭代、内存管理、历史记录
│
├── server/                          # FastAPI 后端
│   ├── shared.py                    # 共享实例与工具类（StaticFiles、Pool、Collector）
│   ├── main.py                      # 主站应用 :8000 — API + WebSocket
│   ├── admin_app.py                 # 后台管理应用 :8010 — 配置 + 监控
│   ├── pool.py                      # Worker 进程池管理 — 任务分发、恢复、统计
│   ├── worker.py                    # 子进程入口 — 加载模型、执行模拟、返回结果
│   ├── store.py                     # 结果存储 — 内存 + 磁盘两级缓存、TTL 过期
│   ├── collector.py                 # 系统监控采集 — CPU/GPU/内存/磁盘/任务
│   └── __init__.py
│
└── web/                             # 前端页面
    ├── index.html                   # 主站页面 — Vue 3 + Tailwind CSS + Plotly.js
    ├── admin.html                   # 后台管理页面 — Vue 3 + Chart.js
    └── js/
        ├── app.js                   # 主站逻辑 — 模型选择、参数调节、任务提交、可视化渲染
        └── admin.js                 # 后台管理逻辑 — Worker 配置、系统监控、图表

start.py                             # 一键启动脚本
Pattern-Generator.spec               # PyInstaller 打包规格
requirements.txt                     # Python 依赖清单
CHANGELOG.md                         # 更新日志
```

## 讨论与交流

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;如果你在使用过程中遇到任何问题，或者有新的功能需求、改进建议，欢迎在 [GitHub Issues](../../issues) 中提出。如果你有相应的解决方法，也非常欢迎提交 Pull Request 帮助我一起完善这个项目！

## 行为准则

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本项目遵循 **Contributor Covenant Code of Conduct**。我们致力于营造一个开放、友好、互相尊重的社区环境。

## 许可证

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本项目采用 **GPL-3.0 License** 开源许可证。详见 [LICENSE](./LICENSE) 文件。