<h1 align="center">
  <br>
  <strong> Pattern Generator — Reaction-Diffusion Equation Visualization Tool</strong>
  <br>
</h1>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/Flask-3.0+-000000?logo=flask&logoColor=white"></a>
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

## Overview

| Feature | Description |
|------|------|
|  GPU Acceleration | PyTorch CUDA backend |
|  Multi-dimensional Visualization | Plotly.js 2D heatmaps / 3D surface plots / time evolution curves |
|  Animated Evolution | Frame-by-frame playback of pattern evolution with pause, speed control, and frame navigation |
|  Parameter Tuning | 7-8 freely adjustable parameters, real-time model switching, one-click reset to defaults |
|  Custom Tracking Points | Place observation points anywhere on the grid to track population density over time |
|  Memory Management | Automatically cleans up GPU memory after simulation to prevent memory leaks |

## Models & Patterns

| Model | Typical Patterns | Parameters | Recommended Iterations |
|------|---------|---------|---------|
| Model 1 · Rosenzweig-MacArthur | Spiral waves, spots | 7 | 9,000 |
| Model 2 · Holling II | Stripes, labyrinth patterns | 8 | 15,000 |
| Model 3 · Ratio-dependent | Spiral waves, target waves | 8 | 15,000 |
| Model 4 · Symmetric competition | Spots, phase separation patterns | 3 | 10,000 |
| Model 5 · Continuous-discrete | Complex dynamic patterns, chaotic patterns | 8 | 4,000 |

## System Requirements

| Item | Minimum Requirement |
|------|---------|
| OS | Windows 10 version 1809 or later / Windows 11 |
| Architecture | 64-bit (x64) |
| Memory | 8GB or more recommended |
| GPU (optional) | NVIDIA GPU + CUDA 12.x+, 4GB+ VRAM |
| Browser | Edge / Chrome / Firefox (for the web UI) |

## Quick Start

### Download & Run

1. Download the latest `.zip` archive from the [Releases](https://github.com/MqKeYan/pattern-generator/releases) page
2. Extract it to any directory (**avoid directories requiring administrator privileges**, e.g., `C:\Program Files`)
3. Note that the extracted `pattern-generator.exe` must be in the same directory as the `_internal/` folder
4. Install the `Pytorch` dependency separately. For CUDA 13.2+ support, run `pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu132`, or visit the [official website](https://pytorch.org/get-started/locally/)
5. Double-click `pattern-generator.exe` and click the URL in the command line to open the page automatically

### Run from Source

```bash
# Requirements: Python 3.13+
git clone https://github.com/MqKeYan/pattern-generator.git
cd pattern-generator
pip install -r requirements.txt

# GPU acceleration
# Check CUDA version info
nvidia-smi
# Install the PyTorch matching your CUDA version
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132

# Start the server
python start.py --host 0.0.0.0
```

After startup, visit **http://localhost:5000** in your browser.

## Usage

1. **Choose a model**: Select one of the 5 models from the dropdown; the parameter panel loads the defaults automatically.
2. **Adjust parameters**: Modify parameter values, click the ↺ button to reset a single parameter, or click "Reset Parameters" to restore all defaults.
3. **Set initial value ranges**: Adjust the initial density ranges of the X/Y populations.
4. **Add tracking points** (optional): Enter grid coordinates (0-99) to observe population changes at specific positions.
5. **Run the simulation**: Adjust the number of iterations, click "Run Simulation", and view the results.
6. **View results**:
   - **2D Patterns**: X/Y population heatmaps + combined pattern + time evolution curves
   - **3D Patterns**: Population density 3D surface plots
   - **Animated Evolution**: Frame-by-frame playback of the pattern formation process

## Project Structure

```
src/                                 # Source code
├── core/                            # Core computation engine
│   ├── config.py                    # Model parameter configuration
│   ├── models.py                    # 5 reaction-diffusion equations + Laplacian operator
│   ├── simulation.py                # Simulation engine — grid initialization, iteration, memory management
│   └── visualization.py             # Visualization data generation — Plotly JSON format
├── port_check.py                    # Port occupancy check
├── web/                             # Web service layer
│   ├── server.py                    # Flask web service — API + page routing
│   ├── static/
│   │   ├── css/style.css            # Dark tech-style theme
│   │   ├── fonts/NotoSansCJK-VF.otf.ttc # Noto Sans CJK variable font
│   │   ├── js/app.js                # Frontend logic — Plotly.js chart rendering
│   │   ├── js/i18n.js               # Internationalization module
│   │   ├── js/plotly.min.js         # Local Plotly.js library
│   │   └── favicon.ico              # Website icon
│   └── templates/
│       └── index.html               # Main page
└── version.py                       # Version management

run.py                               # Startup script
```

## Discussion & Feedback

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;If you encounter any issues while using this project, or have feature requests or improvement suggestions, feel free to open an [issue on GitHub](https://github.com/MqKeYan/pattern-generator/issues). If you have a solution, a Pull Request is also very welcome to help improve this project together!

## Code of Conduct

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;This project follows the **Contributor Covenant Code of Conduct**. We are committed to fostering an open, friendly, and respectful community environment.

## License

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;This project is licensed under the **GPL-3.0 License**. See the [LICENSE](../LICENSE) file for details.