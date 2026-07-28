<h1 align="center">
  <br>
  <strong> 斑图生成器——反应扩散方程可视化工具</strong>
  <br>
</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/Flask-3.0+-000000?logo=flask&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/PyTorch-2.0+-EE4C2C?logo=pytorch&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/Plotly.js-2.32+-3F4F75?logo=plotly&logoColor=white"></a>
</p>

<p align="center">
  <strong> 5 种捕食者-猎物反应扩散模型，GPU 加速模拟，交互式可视化螺旋波、斑点、条纹等斑图形成过程 </strong>
</p>

## 功能概览

| 功能 | 说明 |
|------|------|
|  GPU 加速 | PyTorch CUDA 后端，比纯 CPU 快数十倍 |
|  多维可视化 | Plotly.js 二维热力图 / 三维表面图 / 时间演化曲线 |
|  动画演化 | 逐帧播放斑图演化过程，支持暂停、调速、帧跳转 |
|  参数调优 | 7-8 个参数自由调节，实时切换模型，一键重置默认值 |
|  自定义跟踪点 | 在网格任意位置设置观察点，追踪种群密度随时间变化 |
|  内存管理 | 模拟完成后自动清理 GPU 显存，防止内存泄漏 |

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
| GPU（可选） | NVIDIA GPU + CUDA 12.x+，显存 4GB+ |
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
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132 #下载支持CUDA的Pytorch

# 启动服务
python start.py --host 0.0.0.0
```

启动后浏览器访问 **http://localhost:5000**。

## 使用流程

1. **选择模型**：下拉选择 5 种模型之一，参数面板自动加载默认值
2. **调整参数**：修改参数值，点击 ↺ 按钮重置单个参数，点击「重置参数」恢复全部默认值
3. **设置初始值范围**：调节 X/Y 种群的初始密度范围
4. **添加跟踪点**（可选）：输入网格坐标 (0-99)，观察指定位置的种群变化
5. **运行模拟**：调整迭代次数，点击「运行模拟」，查看结果
6. **查看结果**：
   - **二维斑图**：X种群 / Y种群 热力图 + 合并斑图 + 时间演化曲线
   - **三维斑图**：种群密度 3D 表面图
   - **动画演化**：逐帧播放斑图形成过程

## 项目结构

```
app/                                 # 软件代码
├── config.py                        # 模型参数配置
├── models.py                        # 5 种反应扩散方程 + 拉普拉斯算子
├── simulation.py                    # 模拟引擎 — 网格初始化、迭代、内存管理
├── visualization.py                 # 可视化数据生成 — Plotly JSON 格式
├── server.py                        # FastAPI Web 服务 — API + 页面路由
├── utils.py                         # 环境变量设置
├── version.py                       # 版本号管理
├── static/
│   ├── css/style.css                # 深色科技风主题样式
│   └── js/app.js                    # 前端逻辑 — Plotly.js 图表渲染
└── templates/
    └── index.html                   # 主页面

run.py                               # 启动脚本
```

## 讨论与交流

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;如果你在使用过程中遇到任何问题，或者有新的功能需求、改进建议，欢迎在 [GitHub Issues](../../issues) 中提出。如果你有相应的解决方法，也非常欢迎提交 Pull Request 帮助我一起完善这个项目！

## 行为准则

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本项目遵循 **Contributor Covenant Code of Conduct**。我们致力于营造一个开放、友好、互相尊重的社区环境。

## 许可证

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本项目采用 **GPL-3.0 License** 开源许可证。详见 [LICENSE](./LICENSE) 文件。