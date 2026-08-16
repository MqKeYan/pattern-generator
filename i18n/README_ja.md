<h1 align="center">
  <br>
  <strong> パターン生成器——反応拡散方程式可視化ツール</strong>
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
  注意：インターフェースの言語は機械翻訳です。不正確な箇所があれば、<a href="https://github.com/MqKeYan/pattern-generator/issues">Issues</a> でお知らせください。
</p>

## はじめに

パターン生成器は、反応拡散方程式に基づく可視化ツールで、生態系における捕食者-被食者の個体群の時空間ダイナミクスをシミュレーション・観察するためのものです。5種類の古典的な反応拡散モデルを内蔵し、PyTorch CUDAによるGPU高速化により、渦巻波・斑点・縞模様などの典型的なパターンを素早く生成できます。2次元ヒートマップ・3次元サーフェス図・時間発展曲線などの多様な可視化形式に加え、パターン進化アニメーションのフレーム再生にも対応しています。

## 機能概要

| 機能 | 説明 |
|------|------|
|  GPU高速化 | PyTorch CUDA バックエンド |
|  多次元可視化 | Plotly.js による2次元ヒートマップ / 3次元サーフェス図 / 時間発展曲線 |
|  アニメーション再生 | パターン形成過程をフレーム再生、一時停止・速度調整・フレームジャンプ対応 |
|  パラメータ調整 | 7〜8個のパラメータを自由に調整、モデルをリアルタイム切替、ワンクリックでデフォルト値に戻す |
|  カスタム追跡点 | グリッド上の任意位置に観測点を設置し、個体群密度の時間変化を追跡 |
|  メモリ管理 | シミュレーション完了後にGPUメモリを自動クリアし、メモリリークを防止 |

## モデルとパターン

| モデル | 代表的なパターン | パラメータ数 | 推奨反復回数 |
|------|---------|---------|---------|
| モデル1 · Rosenzweig-MacArthur | 渦巻波、斑点パターン | 7 | 9,000 |
| モデル2 · Holling II | 縞模様、迷路パターン | 8 | 15,000 |
| モデル3 · Ratio-dependent | 渦巻波、標的波 | 8 | 15,000 |
| モデル4 · 対称競争 | 斑点パターン、相分離パターン | 3 | 10,000 |
| モデル5 · 連続化離散 | 複雑な動的パターン、カオスパターン | 8 | 4,000 |

## システム要件

| 項目 | 最低要件 |
|------|---------|
| OS | Windows 10 バージョン1809以降 / Windows 11 |
| アーキテクチャ | 64ビット（x64） |
| メモリ | 8GB以上推奨 |
| GPU（任意） | NVIDIA GPU + CUDA 12.x+、VRAM 4GB以上 |
| ブラウザ | Edge / Chrome / Firefox（Webインターフェース用） |

## クイックスタート

### ダウンロード & 実行

1. [Releases](https://github.com/MqKeYan/pattern-generator/releases) ページから最新版の `.zip` アーカイブをダウンロード
2. 任意のディレクトリに解凍（**管理者権限が必要なディレクトリは避けてください**、例：`C:\Program Files`）
3. 解凍後の `pattern-generator.exe` は `_internal/` フォルダと同じディレクトリに置く必要があります
4. 別途 `Pytorch` の依存関係をインストールします。`CUDA 13.2+` 対応版のインストールコマンドは `pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu132`、または[公式サイト](https://pytorch.org/get-started/locally/)を参照
5. `pattern-generator.exe` をダブルクリックし、コマンドラインのURLをクリックするとページが自動的に開きます

### ソースコードから実行

```bash
# 環境要件：Python 3.13+
git clone https://github.com/MqKeYan/pattern-generator.git
cd pattern-generator
pip install -r requirements.txt

# GPU高速化
# CUDAバージョン情報を確認
nvidia-smi
# 対応するCUDAバージョンのPytorchをインストール
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132

# サーバー起動
python start.py --host 0.0.0.0
```

起動後、ブラウザで **http://localhost:5000** にアクセスしてください。

## 使用方法

1. **モデルを選択**：ドロップダウンから5種類のモデルを選択、パラメータパネルが自動的にデフォルト値を読み込みます
2. **パラメータを調整**：パラメータ値を変更、↺ ボタンで個別パラメータをリセット、「パラメータをリセット」で全デフォルト値に戻します
3. **初期値範囲を設定**：X/Y個体群の初期密度範囲を調整
4. **追跡点を追加**（任意）：グリッド座標（0-99）を入力し、指定位置の個体群変化を観察
5. **シミュレーションを実行**：反復回数を調整、「シミュレーション実行」をクリックして結果を表示
6. **結果を表示**：
   - **2次元パターン**：X個体群 / Y個体群 ヒートマップ + 結合パターン + 時間発展曲線
   - **3次元パターン**：個体群密度の3Dサーフェス図
   - **アニメーション**：パターン形成過程のフレーム再生

## プロジェクト構成

```
src/                                 # ソフトウェアコード
├── core/                            # コア計算エンジン
│   ├── config.py                    # モデルパラメータ設定
│   ├── models.py                    # 5種類の反応拡散方程式 + ラプラシアン
│   ├── simulation.py                # シミュレーションエンジン — グリッド初期化、反復、メモリ管理
│   └── visualization.py             # 可視化データ生成 — Plotly JSON形式
├── port_check.py                    # ポート占有チェック
├── web/                             # Webサービス層
│   ├── server.py                    # Flask Webサービス — API + ページルーティング
│   ├── static/
│   │   ├── css/style.css            # ダークテック風テーマ
│   │   ├── fonts/NotoSansCJK-VF.otf.ttc # Noto Sans CJK 可変フォント
│   │   ├── js/app.js                # フロントエンドロジック — Plotly.js チャート描画
│   │   ├── js/i18n.js               # 国際化翻訳モジュール
│   │   ├── js/plotly.min.js         # ローカルPlotly.jsライブラリ
│   │   └── favicon.ico              # サイトアイコン
│   └── templates/
│       └── index.html               # メインページ
└── version.py                       # バージョン管理

run.py                               # 起動スクリプト
```

## ディスカッションと交流

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;使用中に問題が発生した場合、または新機能のリクエスト・改善提案がある場合は、[GitHub Issues](https://github.com/MqKeYan/pattern-generator/issues) でお知らせください。解決方法があれば、Pull Request を送ってプロジェクトの改善にご協力いただけると大変嬉しいです！

## 行動規範

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本プロジェクトは **Contributor Covenant Code of Conduct** に従います。オープンで友好的、相互尊重のあるコミュニティ環境の構築に努めています。

## ライセンス

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本プロジェクトは **GPL-3.0 License** で提供されています。詳細は [LICENSE](../LICENSE) ファイルを参照してください。