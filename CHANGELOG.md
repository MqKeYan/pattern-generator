# 更新日志

## v1.3.1 (2026-07-25) — 代码审计修复

- **修复**: `StaticFiles` 挂载在根路径，WebSocket 连接触发 `AssertionError` — 包装类忽略非 HTTP scope
- **修复**: `_recover_worker` 竞态条件，池停止后 worker 恢复导致 `IndexError`
- **修复**: `get_job_stats()` 内调用 `get_workers_status()` 导致 Lock 死锁
- **修复**: GPU 显存总量硬编码 8192 MB → 改为动态查询 `torch.cuda.get_device_properties()`
- **修复**: `_disk_scan_counter` 用 `getattr` 动态初始化 → 移到 `__init__` 显式声明
- **修复**: `collector._collect()` 内部每秒 `import torch` → 提升到模块顶部
- **重构**: 共享实例 (`pool`/`collector`/`store`/`StaticFiles`) 抽取到 `server/shared.py`，消除跨模块导入
- **重构**: 版本号统一来源为 `app.__version__`，`start.py`/FastAPI/前端均动态获取；新增 `/api/version` 端点
- **重构**: `collector` 不再直接访问 `pool._lock`/`job_statuses`，改用 `pool.get_job_stats()` 公开 API
- **新增**: `store.delete()` 连接到 `DELETE /api/jobs/{job_id}`，取消任务时清理结果数据
- **新增**: `store.get()` 内存读缓存，避免磁盘大结果反复读盘
- **新增**: 基础测试套件 `tests/` — 41 个测试覆盖模型函数、PoolManager 状态机、ResultStore
- **清理**: 移除 `ws_jobs` 空实现存根（预留注释）；移除 `main.py`/`admin_app.py` 中重复的 StaticFiles 类

## v1.3.0 (2026-07-07) — HTML 前端改造

- **架构变更**: tkinter 桌面应用 → 前后端分离 Web 应用
- **新增 `server/` 后端**: FastAPI Web 服务（main.py + admin_app.py）
- **新增 Worker 进程池**: 多进程隔离，支持 GPU/CPU 资源池，LAN 多人同时使用
- **新增 `web/` 前端**: Vue 3 + Tailwind CSS + Plotly.js + Chart.js
- **主站 (:8000)**: 斑图生成器工作台，提交模拟 + Plotly.js 可视化（2D/3D/动画）
- **后台管理 (:8010)**: Worker 池配置 + 实时系统监控（CPU/GPU/内存/Worker 负载）
- **`start.py`**: 一键启动双端口服务，仅局域网部署
- 移除 matplotlib 依赖，可视化改用 Plotly.js
- 移除旧版 tkinter 代码（app_window/ui_widgets/visualizer/theme/environment/version）
- 新增 `斑图生成器.spec`: PyInstaller 白名单打包文件，直接指令打包

## v1.2.1 (2026-06-29) — 依赖文档完善

- 新增 `requirements.txt`：pip 一键安装依赖清单（torch / numpy / matplotlib / psutil）

## v1.2.0 (2026-06-29) — 动画控制增强

- 添加播放/暂停控制，可随时控制动画
- 状态指示器与动态按钮，实时显示动画状态
- 工具栏快捷控制区，操作更便捷
- 版本控制模块独立，支持语义化版本管理
- 底部状态栏：显示版本号、目录、运行时间、CPU/GPU/内存占用
- 迭代/运行/重置按钮移入二维、三维标签页
- 动画按钮移入"动画演示"标签页
- 标签页重命名：动画演化 → 动画演示
- 参数布局优化：注释与参数名合并显示，编辑框对齐
- 自动清理复选框改为实心选中样式

## v1.1.0 (2025-06-10) — 动画与跟踪点

- 添加动画演化功能，展示斑图随时间变化过程
- 实现多点跟踪功能，可追踪任意格点的时间序列
- 优化颜色映射与显示，提升可视化效果
- 添加内存自动清理，优化长时间运行性能

## v1.0.0 (2025-04-18) — 初始发布

- 实现 5 种捕食者-猎物模型（Rosenzweig-MacArthur、Holling II、Ratio-dependent、对称竞争、离散连续化）
- 基础斑图可视化（二维/三维）
- 深色科学主题界面，高对比度配色方案
- GPU 加速模拟支持
