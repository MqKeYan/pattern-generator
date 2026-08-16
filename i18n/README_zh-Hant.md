<h1 align="center">
  <br>
  <strong> 斑圖生成器——反應擴散方程式視覺化工具</strong>
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
  提示：軟體介面語言由機器翻譯產生，如有不準確之處，歡迎在 <a href="https://github.com/MqKeYan/pattern-generator/issues">Issues</a> 中提出。
</p>

## 簡介

斑圖生成器是一款基於反應擴散方程式的視覺化工具，用於模擬並觀察生態系統中捕食者-獵物族群的時空動態。軟體內建 5 種經典反應擴散模型，藉由 PyTorch CUDA 實現 GPU 加速，可快速生成螺旋波、斑點、條紋等典型斑圖；提供二維熱力圖、三維表面圖與時間演化曲線等多種視覺化形式，並支援逐幀播放斑圖演化動畫。

## 功能總覽

| 功能 | 說明 |
|------|------|
|  GPU 加速 | PyTorch CUDA 後端 |
|  多維視覺化 | Plotly.js 二維熱力圖 / 三維表面圖 / 時間演化曲線 |
|  動畫演化 | 逐幀播放斑圖演化過程，支援暫停、調整速度、跳轉影格 |
|  參數調校 | 7-8 個參數自由調整，即時切換模型，一鍵重設預設值 |
|  自訂追蹤點 | 在網格任意位置設定觀察點，追蹤族群密度隨時間的變化 |
|  記憶體管理 | 模擬完成後自動清理 GPU 記憶體，防止記憶體洩漏 |

## 模型與斑圖

| 模型 | 典型斑圖 | 參數數量 | 建議疊代 |
|------|---------|---------|---------|
| 模型1 · Rosenzweig-MacArthur | 螺旋波、斑點斑圖 | 7 | 9,000 |
| 模型2 · Holling II | 條紋斑圖、迷宮斑圖 | 8 | 15,000 |
| 模型3 · Ratio-dependent | 螺旋波、靶波 | 8 | 15,000 |
| 模型4 · 對稱競爭 | 斑點斑圖、相分離斑圖 | 3 | 10,000 |
| 模型5 · 連續化離散 | 複雜動態斑圖、混沌斑圖 | 8 | 4,000 |

## 系統需求

| 項目 | 最低需求 |
|------|---------|
| 作業系統 | Windows 10 版本 1809 或更新 / Windows 11 |
| 架構 | 64 位元（x64） |
| 記憶體 | 建議 8GB 以上 |
| GPU（選用） | NVIDIA GPU + CUDA 12.x+，記憶體 4GB+ |
| 瀏覽器 | Edge / Chrome / Firefox（存取 Web 介面） |

## 快速開始

### 下載 & 執行

1. 從 [Releases](https://github.com/MqKeYan/pattern-generator/releases) 頁面下載最新版 `.zip` 壓縮檔
2. 解壓縮到任意目錄（**不要放在需要系統管理員權限的目錄**，例如 `C:\Program Files`）
3. 注意解壓縮後的 `pattern-generator.exe` 需要與 `_internal/` 資料夾在同一目錄
4. 另外安裝 `Pytorch` 依賴，支援 `CUDA 13.2+` 版本的指令為 `pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu132`，或前往[官網](https://pytorch.org/get-started/locally/)
5. 雙擊執行 `pattern-generator.exe`，點擊命令列的網址自動開啟頁面

### 從原始碼執行

```bash
# 環境需求：Python 3.13+
git clone https://github.com/MqKeYan/pattern-generator.git
cd pattern-generator
pip install -r requirements.txt

# GPU 加速
# 檢視 CUDA 版本資訊
nvidia-smi
# 下載對應 CUDA 版本的 Pytorch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132

# 啟動服務
python start.py --host 0.0.0.0
```

啟動後，以瀏覽器存取 **http://localhost:5000** 。

## 使用流程

1. **選擇模型**：從下拉選單選擇 5 種模型之一，參數面板會自動載入預設值
2. **調整參數**：修改參數數值，點擊 ↺ 按鈕重設單一參數，點擊「重設參數」還原全部預設值
3. **設定初始值範圍**：調整 X/Y 族群的初始密度範圍
4. **新增追蹤點**（選用）：輸入網格座標（0-99），觀察指定位置的族群變化
5. **執行模擬**：調整疊代次數，點擊「執行模擬」，檢視結果
6. **檢視結果**：
   - **二維斑圖**：X族群 / Y族群 熱力圖 + 合併斑圖 + 時間演化曲線
   - **三維斑圖**：族群密度 3D 表面圖
   - **動畫演化**：逐幀播放斑圖形成過程

## 專案結構

```
src/                                 # 軟體程式碼
├── core/                            # 核心計算引擎
│   ├── config.py                    # 模型參數設定
│   ├── models.py                    # 5 種反應擴散方程式 + 拉普拉斯算子
│   ├── simulation.py                # 模擬引擎 — 網格初始化、疊代、記憶體管理
│   └── visualization.py             # 視覺化資料生成 — Plotly JSON 格式
├── web/                             # Web 服務層
│   ├── server.py                    # Flask Web 服務 — API + 頁面路由
│   ├── static/
│   │   ├── css/style.css            # 深色科技風主題樣式
│   │   ├── fonts/NotoSansCJK-VF.otf.ttc # 思源黑體可變字型
│   │   ├── js/app.js                # 前端邏輯 — Plotly.js 圖表渲染
│   │   ├── js/i18n.js               # 國際化翻譯模組
│   │   ├── js/plotly.min.js         # 本機 Plotly.js 函式庫
│   │   └── favicon.ico              # 網站圖示
│   └── templates/
│       └── index.html               # 主頁面
└── version.py                       # 版本號管理

run.py                               # 啟動指令碼
```

## 討論與交流

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;如果在使用過程中遇到任何問題，或有新的功能需求與改進建議，歡迎在 [GitHub Issues](https://github.com/MqKeYan/pattern-generator/issues) 中提出。如果找到解決方法，也非常歡迎提交 Pull Request 一起完善這個專案！

## 行為準則

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本專案遵循 **Contributor Covenant Code of Conduct**。我們致力於營造開放、友善、互相尊重的社群環境。

## 授權條款

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本專案採用 **GPL-3.0 License** 開源授權條款。詳見 [LICENSE](../LICENSE) 檔案。