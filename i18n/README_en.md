<h1 align="center">
  <br>
  <strong> Pattern Generator — Reaction-Diffusion Equation Visualization Tool</strong>
  <br>
</h1>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/PyTorch-2.0+-EE4C2C?logo=pytorch&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/Plotly.js-2.32+-3F4F75?logo=plotly&logoColor=white"></a>
</p>

<p align="center">
  Languages:
  <a href="../README.md"> 简体中文 </a> ·
  <a href="./README_en.md"> English </a> ·
  <a href="./README_zh-Hant.md"> 繁體中文 </a> ·
  <a href="./README_ja.md"> 日本語 </a> ·
  <a href="./README_ko.md"> 한국어 </a>
</p>

<p align="center">
  Note: The interface language is machine-translated. If you find any inaccuracies, feel free to report them in the <a href="https://github.com/MqKeYan/pattern-generator/issues">Issues</a>.
</p>

## Introduction

Pattern Generator is a visualization tool based on reaction-diffusion equations, designed to simulate and observe the spatiotemporal dynamics of predator-prey populations in ecosystems. It includes 5 classic reaction-diffusion models and leverages PyTorch CUDA for GPU acceleration, enabling rapid generation of typical patterns such as spiral waves, spots, and stripes. It offers multiple visualization forms including 2D heatmaps, 3D surface plots, and time evolution curves, along with frame-by-frame playback of pattern evolution animations.

## Features

### Frontend Visualization
| Feature | Description |
|------|------|
| GPU Acceleration | PyTorch CUDA backend with auto CPU fallback and multi-GPU selection by free VRAM |
| Multi-dimensional Visualization | Plotly.js 2D heatmaps / 3D surfaces / time evolution curves |
| Animated Evolution | Frame-by-frame playback with pause, speed control and frame scrubbing; frame history kept in host memory |
| Parameter Tuning | 7-8 parameters per model, live switching, one-click reset and per-parameter reset |
| Custom Tracking Points | Up to 8 tracking points at any grid position (0-99) to follow population density over time |
| Memory Management | Automatic GPU/host cache cleanup after simulation to prevent leaks |

### Tasks & Scheduling
| Feature | Description |
|------|------|
| Async Task Queue | FIFO scheduling with queue position and real-time progress in the loading overlay; supports “Cancel Task” |
| Timeout & Retry | Auto cancel on timeout (default 300s), auto retry on failure (default 1), dead-letter queue when retries exhausted |
| VRAM Pre-check | Selects GPU by free VRAM + reserve threshold before dispatch; queues if insufficient |
| Cache Restore | Auto restores parameters and charts on refresh, with on-demand 2D/animation restore |

### Admin Center (`http://127.0.0.1:5001` local only)

| Module | Description |
|------|------|
| Overview | Global status, cumulative stats, quick actions and report export |
| Real-time Monitoring | CPU / memory / GPU util / VRAM / temperature / power / disk / network curves (3-min rolling) and peaks |
| Task Queue | Running / waiting / history / dead-letter management with cancel, retry, clear and delete |
| Client Management | Online / offline / paused / queued / computing tracking; pause, kick (and ban IP), clear cache, remarks & tags |
| Access Control | IP / client_id blacklist & whitelist, LAN restriction, IP+client_id rate limiting, denial log |
| Alerting | Windows toast, system sound and PushPlus WeChat push with configurable thresholds and events |
| Logs | Separate file per run `log/YYYY-MM-DD_HH-mm-ss_PID.log` with live view, filtering, search and download |
| System Settings | Ports, concurrency, timeout, retry, rate limit, cache limit and more; supports reset to defaults |

### Operations & Reporting
| Feature | Description |
|------|------|
| WebSocket Push | Metrics / clients / tasks / logs pushed every second with 3-second auto-reconnect |
| Presence | Frontend WebSocket presence (`/api/presence`), offline on disconnect with 5-minute timeout fallback |
| Report Export | Client activity / task execution / resource peaks / access control / alert events as CSV/XLSX/JSON |
| Port Check | Checks main and admin ports on startup with interactive cleanup and 3-second auto-start countdown |

## Models & Patterns

| Model | Typical Patterns | Parameters | Recommended Iterations |
|------|---------|---------|---------|
| Model 1 · Rosenzweig-MacArthur | Spiral waves, spots | 7 | 9,000 |
| Model 2 · Holling II | Stripes, labyrinth | 8 | 15,000 |
| Model 3 · Ratio-dependent | Spiral waves, target waves | 8 | 15,000 |
| Model 4 · Symmetric competition | Spots, phase separation | 3 | 10,000 |
| Model 5 · Continuous-discrete | Complex dynamic, chaotic | 8 | 4,000 |

## System Requirements

| Item | Minimum Requirement |
|------|---------|
| OS | Windows 10 version 1809 or later / Windows 11 |
| Architecture | 64-bit (x64) |
| Memory | 8GB or more recommended |
| GPU (optional) | NVIDIA GPU + CUDA 12.x+, 4GB+ VRAM (auto fallback to CPU) |
| Browser | Edge / Chrome / Firefox (for the web UI) |
| Network | Admin is local only `127.0.0.1:5001`; main UI supports LAN `0.0.0.0:5000` |

## Quick Start

### Download & Run

1. Download the latest `.zip` archive from the [Releases](https://github.com/MqKeYan/pattern-generator/releases) page
2. Extract it to any directory (**avoid directories requiring administrator privileges**, e.g., `C:\Program Files`)
3. Note that the extracted `pattern-generator.exe` must be in the same directory as the `_internal/` folder
4. Install the `Pytorch` dependency separately. For CUDA 13.2+ support, run `pip3 install torch --index-url https://download.pytorch.org/whl/cu132`, or visit the [official website](https://pytorch.org/get-started/locally/)
5. Double-click `pattern-generator.exe` and follow the port check and auto-open browser prompts
6. Main UI: `http://LAN_IP:5000`, Admin: `http://127.0.0.1:5001` (local only)

### Run from Source

```bash
# Requirements: Python 3.13+
git clone https://github.com/MqKeYan/pattern-generator.git
cd pattern-generator
pip install -r requirements.txt

# GPU acceleration (optional)
# Check CUDA version
nvidia-smi
# Install PyTorch matching your CUDA version
pip install torch --index-url https://download.pytorch.org/whl/cu132

# Start services (main + admin together)
python run.py
```

After startup, visit Main UI http://localhost:5000 and Admin http://127.0.0.1:5001.

> Developer note: `run.py` starts two Uvicorn services; restart is required after editing `config/settings.json` in the admin.

## Usage

1. **Choose a model**: Select one of the 5 models from the dropdown; the parameter panel loads the defaults automatically.
2. **Adjust parameters**: Modify parameter values, click the ↺ button to reset a single parameter, or click “Reset Parameters” to restore all defaults.
3. **Set initial value ranges**: Adjust the initial density ranges of the X/Y populations.
4. **Add tracking points** (optional): Enter grid coordinates (0-99) to observe population changes at specific positions.
5. **Run the simulation**: Adjust the number of iterations, click “Run Simulation”, and watch the queue position and real-time progress (`Running, xx%`) in the loading overlay; you can “Cancel Task” at any time.
6. **View results**:
   - **2D Patterns**: X/Y population heatmaps + combined pattern + time evolution curves
   - **3D Patterns**: Population density 3D surface plots (rotatable)
   - **Animated Evolution**: Frame-by-frame playback of the pattern formation process, with play/pause, frame slider and speed control

## Admin Center

Accessible only locally at `http://127.0.0.1:5001`. The left status card shows uptime, ports, online clients and running/waiting tasks in real time.

- **Overview**: Key metric cards, online client stats, cumulative compute time, quick actions and report export.
- **Real-time Monitoring**: Four chart groups for CPU/memory/process memory, GPU util/VRAM, GPU temp/power/CPU temp, disk/network rates, plus a local online-client curve.
- **Task Queue**: Four tables for running / waiting / history / dead letters with per-task actions, GPU assignment and retry count.
- **Client Management**: UUID, name, IP, status, current task, request and success/failure/cancel stats, online duration, tags and remarks; supports pause/resume, kick & ban, clear cache and remarks.
- **Access Control**: Blacklist/whitelist by IP and client_id, LAN private-range restriction and rate-limit settings.
- **Alerting**: Configurable `system_toast` / `system_sound` / `pushplus` with thresholds for queue backlog and GPU temperature.
- **Logs**: Live stream and historical file download with level and keyword filtering.
- **System Settings**: Ports, concurrency, timeout, retry, rate limit, VRAM reserve, result TTL, cache limit, notifications and more.

## Project Structure

```
src/                                 # Source code
├── core/                            # Core computation engine
│   ├── config.py                    # Model parameter configuration
│   ├── models.py                    # 5 reaction-diffusion equations + Laplacian operator
│   ├── simulation.py                # Simulation engine — grid init, iteration, memory management
│   └── visualization.py             # Visualization data generation — Plotly JSON format
├── admin/                           # Admin center
│   ├── server.py                    # Admin FastAPI service
│   ├── clients.py                   # Client status and statistics
│   ├── tasks.py                     # Async task queue and scheduling
│   ├── monitor.py                   # System resource monitoring
│   ├── access_control.py            # Access control
│   ├── notifications.py             # Alert notifications
│   ├── reports.py                   # Report export
│   ├── logger.py                    # Logging system
│   ├── websocket.py                 # WebSocket push
│   ├── static/                      # Admin static assets
│   └── templates/admin.html         # Admin page
├── web/                             # Web service layer
│   ├── server.py                    # Main FastAPI service — API + page routing
│   ├── static/
│   │   ├── css/style.css            # Dark tech theme
│   │   ├── fonts/NotoSansCJK-VF.otf.ttc # Noto Sans CJK variable font
│   │   ├── js/app.js                # Frontend logic — Plotly.js chart rendering
│   │   ├── js/i18n.js               # Internationalization module
│   │   ├── js/plotly.min.js         # Local Plotly.js library
│   │   └── favicon.ico              # Website icon
│   └── templates/
│       └── index.html               # Main page
├── common/                          # Common modules
│   ├── app_context.py               # Shared runtime context
│   ├── config.py                    # Settings, version and runtime paths
│   ├── persistence.py               # JSON atomic persistence
│   ├── security.py                  # Origin, session and access key validation
│   └── startup.py                   # Startup checks (port occupancy + single instance)

run.py                               # Startup script (dual services)
pattern-generator.spec                # PyInstaller build config
requirements.txt                      # Dependency list
```

## Discussion & Exchange

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;If you encounter any issues while using this project, or have feature requests or improvement suggestions, feel free to open an [issue on GitHub](https://github.com/MqKeYan/pattern-generator/issues). If you have a solution, a Pull Request is also very welcome to help improve this project together!

## Code of Conduct

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;This project follows the [**Contributor Covenant Code of Conduct**](../CODE_OF_CONDUCT.md). We are committed to fostering an open, friendly, and respectful community environment.

## License

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;This project is licensed under the **GPL-3.0 License**. See the [LICENSE](../LICENSE) file for details.
