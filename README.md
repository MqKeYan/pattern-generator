<h1 align="center">
  <br>
  <strong> 斑图生成器——反应扩散方程可视化工具</strong>
  <br>
</h1>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/计算引擎-7%20种-EE4C2C"></a>
  <a href="#"><img src="https://img.shields.io/badge/界面-FastAPI%20%2B%20Plotly.js-009688"></a>
</p>

<p align="center">
  Languages:
  <a href="./README.md"> 简体中文 </a> ·
  <a href="./i18n/README_en.md"> English </a> ·
  <a href="./i18n/README_zh-Hant.md"> 繁體中文 </a> ·
  <a href="./i18n/README_ja.md"> 日本語 </a> ·
  <a href="./i18n/README_ko.md"> 한국어 </a>
</p>

<p align="center">
  提示：软件界面语言由机器翻译生成，如有不准确之处，欢迎在 <a href="../../issues">Issues</a> 中提出。
</p>

## 简介

斑图生成器 v2.0.0 是基于反应扩散方程的可视化工具，用于模拟并观察捕食者—猎物及竞争种群的时空动态。软件内置 5 种模型，支持 PyTorch、CuPy、NVIDIA Warp、Taichi、PyOpenCL、Numba、NumPy 共 7 种计算引擎；可生成螺旋波、斑点、条纹等斑图，并展示二维热力图、三维表面图、时间演化曲线和逐帧动画。主界面供浏览器访问，后台负责统一选择计算环境、管理客户端与任务、监控资源和导出报表。

## 功能概览

### 前台可视化
| 功能 | 说明 |
|------|------|
| 计算引擎 | PyTorch、CuPy、NVIDIA Warp、Taichi、PyOpenCL、Numba、NumPy；由后台统一选择，全体客户端使用同一个引擎 |
| 多维可视化 | Plotly.js 二维热力图 / 三维表面图 / 时间演化曲线 |
| 动画演化 | 逐帧播放斑图演化过程，支持暂停、调速、帧跳转；结果在服务端按块缓存，进入动画页时浏览器读取帧块 |
| 参数调优 | 7-8 个参数自由调节，实时切换模型，一键重置默认值，支持单参数重置 |
| 自定义跟踪点 | 在网格任意位置（0-99）设置最多 8 个观察点，追踪种群密度随时间变化 |
| 结果缓存 | 模拟结果写入磁盘缓存，按保留时间和容量清理；刷新页面可恢复当前客户端的缓存结果 |

### 任务与调度
| 功能 | 说明 |
|------|------|
| 异步任务队列 | FIFO 调度，支持排队位置与执行进度实时显示，加载遮罩提供“取消任务” |
| 超时与重试 | 任务超时（默认 300s）自动取消，失败自动重试（默认 1 次），重试耗尽进入死信队列 |
| 显存预检 | 任务分发前按空闲显存 + 预留阈值选择 GPU，不足则继续排队 |
| 缓存恢复 | 刷新页面自动恢复参数与图表数据，支持二维/动画按需恢复 |
| 自动并发 | 每次启动根据当前引擎使用的物理 CPU 插槽数或可独立寻址的 GPU 数量确定任务并发上限；不同任务可分配至不同 GPU，单个任务不跨卡加速 |

### 后台管理中心（`http://127.0.0.1:5001` 仅本机）

| 模块 | 说明 |
|------|------|
| 概览 | 全局状态、累计统计、快捷操作、报表导出入口 |
| 实时监控 | CPU/内存/GPU 利用率、显存、可获取的温度与功耗、磁盘和网络曲线及峰值汇总；默认显示 3 分钟窗口 |
| 任务队列 | 运行中/等待中/历史/死信队列管理，支持取消、重试、清空、删除 |
| 客户端管理 | 在线/离线/暂停/排队/计算状态追踪；暂停、踢出（同时封禁 IP）、缓存清理、备注标签 |
| 访问控制 | IP / client_id 黑白名单、局域网限制、IP+client_id 限流、拒绝记录 |
| 告警通知 | Windows 弹窗、系统提示音、PushPlus、Webhook、SMTP、Telegram、Discord、钉钉、飞书、企业微信，可配置阈值与事件 |
| 日志 | 每次运行独立落盘 `log/YYYY-MM-DD_HH-mm-ss_PID.log`，支持实时查看、过滤、搜索与下载 |
| 系统设置 | 全局 Python/计算引擎/设备、服务端口、监控视图、超时、限流、缓存上限等设置，支持按功能恢复默认；并发上限只显示，不提供手动编辑 |

### 运维与报表
| 功能 | 说明 |
|------|------|
| WebSocket 实时推送 | 后台监控、客户端、任务与日志实时更新，连接中断后尝试重连 |
| 在线状态 | 前台 WebSocket 在线连接（`/api/presence`），断开即离线；5 分钟超时兜底 |
| 报表导出 | 客户端活动 / 任务执行 / 系统资源峰值 / 访问控制 / 告警事件，支持 CSV/XLSX/JSON |
| 端口检测 | 启动时检测主服务与后台端口占用，支持交互清理与 3 秒倒计时自动启动 |

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
| GPU（可选） | 按所选引擎准备相应 GPU、驱动和运行环境；CPU 引擎无需 GPU，显式选择不可用的引擎或设备会提示错误 |
| 浏览器 | Edge / Chrome / Firefox（访问 Web 界面） |
| 网络 | 后台管理中心仅本机 `127.0.0.1:5001`，主界面支持局域网 `0.0.0.0:5000` |

## 快速开始

### 下载 & 运行

1. 从 [Releases](../../releases) 页面下载最新版 `.zip` 压缩包
2. 解压到任意目录（**不要放在需要管理员权限的目录**，如 `C:\Program Files`）
3. 注意解压后的 `pattern-generator.exe` 需要和 `_internal/` 文件夹在同一目录
4. 安装 64 位系统 Python 3.13 或更新版本，并在该解释器中按需安装计算引擎，见 [计算依赖说明](docs/compute-engines.md)。发行包不会打包第三方计算引擎运行库；应用自带的 NumPy 只供结果处理和可视化，不代表外部 Python 中的 NumPy 计算引擎可用。高于 3.13 的 Python 仍需确认目标引擎依赖可以安装并通过实际运算检测。
5. 双击运行 `pattern-generator.exe`，按提示完成端口检测与浏览器自动打开设置；命令行依次显示独立的“Python 环境”和“计算引擎”页面。每页均可回车立即继续，或等待 3 秒自动继续；倒计时内按 `n` 可进入选择界面
6. 主界面：`http://局域网IP:5000`，后台：`http://127.0.0.1:5001`（仅本机）


### 从源码运行

```powershell
# 环境要求：64 位系统 Python 3.13 或更新版本；替换成自己的 python.exe 绝对路径
$projectPython = 'C:\完整路径\python.exe'
git clone https://github.com/MqKeYan/pattern-generator.git
cd pattern-generator
& $projectPython -m pip install -r requirements.txt

# 可选：按 requirements.txt 的注释清单选择外部计算引擎，手动安装；以下为 PyTorch CPU 示例
& $projectPython -m pip install "numpy>=2.4,<2.6" "torch==2.14.0+cpu" --extra-index-url https://download.pytorch.org/whl/cpu

# 启动服务（同时启动主服务与后台）
& $projectPython run.py
```

启动后按控制台公布的网址访问主界面（局域网 IP），后台为 http://127.0.0.1:5001。

> `run.py` 同时启动两个 Uvicorn 服务。计算引擎默认设置影响新提交的任务，已提交任务保持原配置；端口等启动项仍需重启生效。

首次启动时，“Python 环境”页按 `n` 可扫描候选解释器，按数字序号选择路径，末项支持手动输入绝对路径；回车或等待 3 秒使用自动默认。后续启动该页只验证当前 Python，按 `n` 才重新扫描。随后“计算引擎”页首次同步搜索七种引擎；之后只验证上次使用的引擎，失效时才全面重扫。该页倒计时内按 `n` 可查看可用引擎并按数字序号选择，直接回车或等待 3 秒继续。后台“系统设置”也能修改全局引擎、设备、Python 路径并手动全面刷新；网页客户端只能查看当前选择。

自动模式在只有一个可用引擎时选用它；多个引擎可用且包含 PyTorch 时优先 PyTorch，其余依次为 CuPy、NVIDIA Warp、Taichi、PyOpenCL、Numba、NumPy。用户手动选定的引擎或 Python 路径如果失效，设置会保留并显示错误，不会悄悄改选。切换全局计算设置及全面刷新时，需先等待已提交任务结束。Numba 目前是 CPU 后端；GPU 能力取决于具体引擎、设备与驱动，当前项目的 GPU 实测仍需在目标硬件上完成。

逐批验收见[第一批](docs/compute-batch-1-review.md)、[第二批](docs/compute-batch-2-review.md)、[第三批](docs/compute-batch-3-review.md)和[第四批](docs/compute-batch-4-review.md)记录。第四批已完成当前电脑上的发行包与 CPU 验证；GPU 实测留待换机。

### 配置文件与数据位置

服务端配置保存在软件运行目录（发行包中为 `pattern-generator.exe` 所在目录，源码运行时为项目根目录）的 `config/`。首次运行会自动创建缺少的功能文件；每次启动读取时会按当前版本补齐新增字段、替换无效值并移除已废弃的功能字段，同时保留已有的有效用户设置。无法归类的旧版扩展字段会转存至 `misc.json`。读取优先级为功能文件中的有效值、旧版配置迁移值、内置默认值。JSON 标准不支持 `//` 注释，因此各现用文件由软件自动加入 `_说明` 字段，保持标准 JSON 可解析。说明语言取操作系统界面语言，支持简体中文、繁体中文、英语、日语和韩语，其他语言回退英语；首次生成文件时即写入，后续每次启动只轻量检查一次，缺失或不完整时才补齐。状态及统计文件只补说明，不重置其业务数据；仅在实际使用时创建的状态文件不会因说明检查而提前生成。通过后台或命令行保存设置时，软件只更新对应功能文件；手动编辑 JSON 请在软件退出后进行。

| 文件 | 用途 |
|------|------|
| `config/startup.json` | 主界面和后台端口、启动时自动打开浏览器 |
| `config/compute.json` | 全局计算引擎、设备、外部 Python 选择 |
| `config/monitor.json` | 监控默认视图和采样时间窗 |
| `config/tasks.json` | 任务超时、重试、队列/结果缓存限制、显存预留；最大并发数由启动时识别，不在此手动设置 |
| `config/access.json` | 允许的主机、请求限流、客户端与连接数限制 |
| `config/notifications.json` | 后台告警渠道、凭据、事件与阈值 |
| `config/blacklist.json`、`config/whitelist.json` | 访问控制黑白名单 |
| `config/compute-engine-state.json`、`config/compute-python-state.json` | 上次启动使用的引擎/Python 状态；按需创建，不覆盖手动选择 |
| `config/stats.json` | 客户端统计与资源峰值，属于运行数据，不建议手动编辑 |
| `config/instance.lock` | 运行时单实例锁，正常退出后移除 |

旧版单文件 `settings.json` 仍可在首次读取时自动迁移，迁移完成才保存为 `settings.legacy*.json` 备份；这些备份不参与正常配置读取，可在核对新文件后清理。若旧版有额外字段，软件可能生成 `config/misc.json` 予以保留；无效的 JSON 可能留下 `.bad-...` 副本。**浏览器的语言、模型参数和个人通知偏好保存在各客户端浏览器本地，不属于服务端 `config/`。**日志在 `log/`，结果与计算编译缓存是可清理的运行数据。更完整的迁移规则见[配置文件说明](docs/config-files.md)。

## 使用流程

1. **选择模型**：下拉选择 5 种模型之一，参数面板自动加载默认值
2. **调整参数**：修改参数值，点击 ↺ 按钮重置单个参数，点击「重置参数」恢复全部默认值
3. **设置初始值范围**：调节 X/Y 种群的初始密度范围
4. **添加跟踪点**（可选）：输入网格坐标 (0-99)，观察指定位置的种群变化
5. **运行模拟**：调整迭代次数，点击「运行模拟」，查看加载遮罩中的排队位置与实时进度（`执行中，进度 xx%`），可随时“取消任务”
6. **查看结果**：
   - **二维斑图**：X种群 / Y种群 热力图 + 合并斑图 + 时间演化曲线
   - **三维斑图**：种群密度 3D 表面图（支持旋转）
   - **动画演化**：逐帧播放斑图形成过程，支持播放/暂停、帧滑块、速度调节

## 后台管理中心

仅本机可访问 `http://127.0.0.1:5001`，左侧全局状态卡实时显示运行时长、端口、在线客户端、运行/等待任务数。

- **概览**：CPU/GPU/内存等关键指标卡、在线客户端统计、累计计算时长、快捷操作与报表导出。
- **实时监控**：CPU/内存/进程内存、GPU 利用率/显存、GPU 温度/功耗/CPU 温度、磁盘/网络速率四组曲线，在线客户端数曲线本地滚动。
- **任务队列**：运行中/等待中/历史/死信四表，支持按任务 ID 操作，显示 GPU 分配与重试次数。
- **客户端管理**：展示 UUID、名称、IP、状态、当前任务、请求与成功/失败/取消统计、在线时长、标签备注；支持暂停/恢复、踢出封禁、清缓存、备注。
- **访问控制**：黑白名单按 IP 与 client_id 维护，支持局域网私有网段限制与限流配置。
- **告警通知**：可配置 `system_toast` / `system_sound` / `pushplus` 及 Webhook、SMTP、Telegram、Discord、钉钉、飞书、企业微信渠道，阈值如队列积压、GPU 温度。
- **日志**：实时流与历史文件下载，支持级别与关键词过滤。
- **系统设置**：端口、超时、重试、限流、显存预留、结果保留时长、缓存上限、通知等。最大并发计算数量每次启动按所选引擎使用的物理 CPU 或可并行 GPU 数量识别，显示在主界面和后台左上角信息卡片；多块 GPU 可同时处理不同客户端的任务，单个任务不跨卡加速。

## 项目结构

```
pattern-generator/
├── run.py                           # 命令行启动、预检与双服务入口
├── src/
│   ├── common/
│   │   ├── config.py                # 版本、配置目录、分文件读写和旧配置迁移
│   │   ├── compute.py               # 外部 Python 查找、引擎探测与全局选择
│   │   ├── app_context.py           # 共享状态、自动并发容量与任务上下文
│   │   ├── startup.py               # 端口和单实例检查
│   │   ├── persistence.py           # JSON 持久化
│   │   ├── security.py              # 访问与会话校验
│   │   └── notification_channels.py # 通知渠道适配
│   ├── core/
│   │   ├── config.py / models.py    # 五种模型的参数与方程
│   │   ├── engines.py               # 七种引擎的统一接口与实际运算探测
│   │   ├── numba_kernels.py         # Numba CPU 内核
│   │   ├── warp_kernels.py          # NVIDIA Warp CPU/CUDA 内核
│   │   ├── taichi_kernels.py        # Taichi CPU/CUDA/Vulkan 内核
│   │   ├── opencl_kernels.cl        # PyOpenCL 计算内核
│   │   ├── simulation.py            # 网格迭代与模拟流程
│   │   ├── external_worker.py       # 外部 Python 执行的计算入口
│   │   ├── task_worker.py           # 独立任务进程
│   │   └── visualization.py         # 图表数据生成
│   ├── web/
│   │   ├── server.py                # 前台 FastAPI 接口与页面路由
│   │   ├── templates/              # 主界面及页面组件
│   │   └── static/                 # 前台 CSS/JS、共用组件和本地 Plotly.js
│   └── admin/
│       ├── server.py                # 后台 FastAPI 接口与页面路由
│       ├── tasks.py / clients.py    # 队列调度与客户端管理
│       ├── monitor.py / reports.py  # 资源监控与报表导出
│       ├── access_control.py        # 黑白名单与访问控制
│       ├── notifications.py         # 后台告警
│       ├── result_store.py          # 结果磁盘缓存
│       ├── logger.py / websocket.py # 日志与实时消息
│       ├── templates/              # 后台页面及组件
│       └── static/                 # 后台 CSS/JS
├── config/                          # 按功能分开的服务端配置及状态
├── requirements.txt                 # 应用依赖及注释的可选计算引擎清单
├── requirements-build.txt           # 打包构建依赖
├── pattern-generator.spec           # PyInstaller 打包配置
└── docs/                            # 计算引擎、配置及分批验收说明
```


## 讨论与交流

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;如果你在使用过程中遇到任何问题，或者有新的功能需求、改进建议，欢迎在 [GitHub Issues](../../issues) 中提出。如果你有相应的解决方法，也非常欢迎提交 Pull Request 帮助我一起完善这个项目！

## 行为准则

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本项目遵循 [**Contributor Covenant Code of Conduct**](CODE_OF_CONDUCT.md)。我们致力于营造一个开放、友好、互相尊重的社区环境。

## 许可证

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本项目采用 **GPL-3.0 License** 开源许可证。详见 [LICENSE](./LICENSE) 文件。
