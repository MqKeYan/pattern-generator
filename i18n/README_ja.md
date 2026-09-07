<h1 align="center">
  <br>
  <strong> パターン生成器——反応拡散方程式可視化ツール</strong>
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
  注意：インターフェースの言語は機械翻訳です。不正確な箇所があれば、<a href="https://github.com/MqKeYan/pattern-generator/issues">Issues</a> でお知らせください。
</p>

## はじめに

パターン生成器は、反応拡散方程式に基づく可視化ツールで、生態系における捕食者-被食者の個体群の時空間ダイナミクスをシミュレーション・観察するためのものです。5種類の古典的な反応拡散モデルを内蔵し、PyTorch CUDAによるGPU高速化により、渦巻波・斑点・縞模様などの典型的なパターンを素早く生成できます。2次元ヒートマップ・3次元サーフェス図・時間発展曲線などの多様な可視化形式に加え、パターン進化アニメーションのフレーム再生にも対応しています。

## 機能概要

### フロントエンド可視化
| 機能 | 説明 |
|------|------|
| GPU 高速化 | PyTorch CUDA バックエンド、CUDA / CPU 自動判定、空き VRAM によるマルチ GPU 選択 |
| 多次元可視化 | Plotly.js による2次元ヒートマップ / 3次元サーフェス図 / 時間発展曲線 |
| アニメーション再生 | パターン形成過程をフレーム再生、一時停止・速度調整・フレームジャンプ対応、フレーム履歴はホストメモリに保持 |
| パラメータ調整 | モデルごとに7〜8個のパラメータを自由に調整、リアルタイム切替、ワンクリック初期化と個別リセット |
| カスタム追跡点 | グリッド上の任意位置（0-99）に最大8点の観測点を設置し、個体群密度の時間変化を追跡 |
| メモリ管理 | シミュレーション完了後にGPUメモリとホストキャッシュを自動クリアし、メモリリークを防止 |

### タスクとスケジューリング
| 機能 | 説明 |
|------|------|
| 非同期タスクキュー | FIFO スケジューリング、待ち位置と実行進捗をローディングオーバーレイにリアルタイム表示、「タスクをキャンセル」対応 |
| タイムアウトとリトライ | タイムアウト（既定 300s）で自動キャンセル、失敗時の自動リトライ（既定 1回）、リトライ超過後はデッドレターキューへ |
| VRAM 事前チェック | タスク投入前に空き VRAM + 予約閾値で GPU を選択、不足時はキューに留まる |
| キャッシュ復元 | ページ更新時にパラメータとチャートを自動復元、2次元/アニメーションはオンデマンド復元 |

### 管理センター（`http://127.0.0.1:5001` ローカルのみ）

| モジュール | 説明 |
|------|------|
| 概要 | グローバル状態、累計統計、クイック操作とレポート出力 |
| リアルタイム監視 | CPU / メモリ / GPU 使用率 / VRAM / 温度 / 電力 / ディスク / ネットワークのリアルタイムカーブ（3分間ローリング）とピーク集計 |
| タスクキュー | 実行中 / 待機中 / 履歴 / デッドレターの管理、キャンセル・リトライ・クリア・削除 |
| クライアント管理 | オンライン / オフライン / 一時停止 / 待機中 / 計算中の追跡、一時停止、キック（IP 同時ブロック）、キャッシュクリア、備考とタグ |
| アクセス制御 | IP / client_id のブラックリスト・ホワイトリスト、LAN 制限、IP+client_id レート制限、拒否ログ |
| アラート通知 | Windows トースト、システムサウンド、PushPlus WeChat プッシュ、閾値とイベント設定可能 |
| ログ | 実行ごとに独立した `log/YYYY-MM-DD_HH-mm-ss_PID.log`、リアルタイム表示、フィルタ・検索・ダウンロード |
| システム設定 | ポート、同時実行数、タイムアウト、リトライ、レート制限、キャッシュ上限など、デフォルト復元対応 |

### 運用とレポート
| 機能 | 説明 |
|------|------|
| WebSocket プッシュ | メトリクス / クライアント / タスク / ログを毎秒プッシュ、切断時は3秒で自動再接続 |
| プレゼンス | フロントエンド WebSocket プレゼンス（`/api/presence`）、切断時に即オフライン、5分タイムアウトでフォールバック |
| レポート出力 | クライアント活動 / タスク実行 / システムリソースピーク / アクセス制御 / アラートイベントを CSV/XLSX/JSON で出力 |
| ポートチェック | 起動時にメインと管理のポート占有をチェック、対話的なクリーンアップと3秒カウントダウンで自動起動 |

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
| GPU（任意） | NVIDIA GPU + CUDA 12.x+、VRAM 4GB以上（GPU なしは自動で CPU にフォールバック） |
| ブラウザ | Edge / Chrome / Firefox（Webインターフェース用） |
| ネットワーク | 管理センターはローカルのみ `127.0.0.1:5001`、メイン画面は LAN `0.0.0.0:5000` 対応 |

## クイックスタート

### ダウンロード & 実行

1. [Releases](https://github.com/MqKeYan/pattern-generator/releases) ページから最新版の `.zip` アーカイブをダウンロード
2. 任意のディレクトリに解凍（**管理者権限が必要なディレクトリは避けてください**、例：`C:\Program Files`）
3. 解凍後の `pattern-generator.exe` は `_internal/` フォルダと同じディレクトリに置く必要があります
4. 別途 `Pytorch` の依存関係をインストールします。`CUDA 13.2+` 対応版のインストールコマンドは `pip3 install torch --index-url https://download.pytorch.org/whl/cu132`、または[公式サイト](https://pytorch.org/get-started/locally/)を参照
5. `pattern-generator.exe` をダブルクリックし、ポートチェックとブラウザ自動起動の案内に従ってください
6. メイン画面：`http://LAN_IP:5000`、管理センター：`http://127.0.0.1:5001`（ローカルのみ）

### ソースコードから実行

```bash
# 環境要件：Python 3.13+
git clone https://github.com/MqKeYan/pattern-generator.git
cd pattern-generator
pip install -r requirements.txt

# GPU高速化（任意）
# CUDAバージョン情報を確認
nvidia-smi
# 対応するCUDAバージョンのPytorchをインストール
pip install torch --index-url https://download.pytorch.org/whl/cu132

# サービス起動（メイン + 管理を同時起動）
python run.py
```

起動後、ブラウザで **メイン http://localhost:5000**、**管理 http://127.0.0.1:5001** にアクセスしてください。

> 開発者向けメモ：`run.py` は2つの Uvicorn サービスを同時起動します。管理画面で `config/settings.json` を変更した後は再起動が必要です。

## 使用方法

1. **モデルを選択**：ドロップダウンから5種類のモデルを選択、パラメータパネルが自動的にデフォルト値を読み込みます
2. **パラメータを調整**：パラメータ値を変更、↺ ボタンで個別パラメータをリセット、「パラメータをリセット」で全デフォルト値に戻します
3. **初期値範囲を設定**：X/Y個体群の初期密度範囲を調整
4. **追跡点を追加**（任意）：グリッド座標（0-99）を入力し、指定位置の個体群変化を観察
5. **シミュレーションを実行**：反復回数を調整、「シミュレーション実行」をクリックし、待ち位置とリアルタイム進捗（`実行中、進捗 xx%`）をローディング表示で確認、必要に応じて「タスクをキャンセル」
6. **結果を表示**：
   - **2次元パターン**：X個体群 / Y個体群 ヒートマップ + 結合パターン + 時間発展曲線
   - **3次元パターン**：個体群密度の3Dサーフェス図（回転可能）
   - **アニメーション**：パターン形成過程のフレーム再生、再生/一時停止・フレームスライダー・速度調整に対応

## 管理センター

ローカルのみ `http://127.0.0.1:5001` でアクセス可能。左側のグローバル状態カードに稼働時間、ポート、オンラインクライアント、実行/待機タスク数がリアルタイム表示されます。

- **概要**：主要メトリクス、オンライン統計、累計計算時間、クイック操作とレポート出力。
- **リアルタイム監視**：CPU/メモリ/プロセスメモリ、GPU 使用率/VRAM、GPU 温度/電力/CPU 温度、ディスク/ネットワークの4グループのカーブと、オンラインクライアント数のローカルカーブ。
- **タスクキュー**：実行中 / 待機中 / 履歴 / デッドレターの4テーブル、タスクごとの操作、GPU 割り当てとリトライ回数。
- **クライアント管理**：UUID、名前、IP、状態、現在のタスク、リクエストと成功/失敗/キャンセル統計、オンライン時間、タグと備考、一時停止/再開、キックとブロック、キャッシュクリア、備考。
- **アクセス制御**：IP と client_id によるブラックリスト/ホワイトリスト、LAN プライベート範囲制限とレート制限設定。
- **アラート通知**：`system_toast` / `system_sound` / `pushplus` を設定可能、キュー滞留や GPU 温度などの閾値。
- **ログ**：ライブストリームと履歴ファイルのダウンロード、レベルとキーワードフィルタ。
- **システム設定**：ポート、同時実行数、タイムアウト、リトライ、レート制限、VRAM 予約、結果保持期間、キャッシュ上限、通知など。

## プロジェクト構成

```
src/                                 # ソフトウェアコード
├── core/                            # コア計算エンジン
│   ├── config.py                    # モデルパラメータ設定
│   ├── models.py                    # 5種類の反応拡散方程式 + ラプラシアン
│   ├── simulation.py                # シミュレーションエンジン — グリッド初期化、反復、メモリ管理
│   └── visualization.py             # 可視化データ生成 — Plotly JSON形式
├── admin/                           # 管理センター
│   ├── server.py                    # 管理 FastAPI サービス
│   ├── clients.py                   # クライアント状態と統計
│   ├── tasks.py                     # 非同期タスクキューとスケジューリング
│   ├── monitor.py                   # システムリソース監視
│   ├── access_control.py            # アクセス制御
│   ├── notifications.py             # アラート通知
│   ├── reports.py                   # レポート出力
│   ├── logger.py                    # ログシステム
│   ├── websocket.py                 # WebSocket プッシュ
│   ├── static/                      # 管理静的ファイル
│   └── templates/admin.html         # 管理ページ
├── web/                             # Webサービス層
│   ├── server.py                    # メイン FastAPI サービス — API + ページルーティング
│   ├── static/
│   │   ├── css/style.css            # ダークテック風テーマ
│   │   ├── fonts/NotoSansCJK-VF.otf.ttc # Noto Sans CJK 可変フォント
│   │   ├── js/app.js                # フロントエンドロジック — Plotly.js チャート描画
│   │   ├── js/i18n.js               # 国際化翻訳モジュール
│   │   ├── js/plotly.min.js         # ローカルPlotly.jsライブラリ
│   │   └── favicon.ico              # サイトアイコン
│   └── templates/
│       └── index.html               # メインページ
├── common/                          # 共通モジュール
│   ├── app_context.py               # 共有ランタイムコンテキスト
│   ├── config.py                    # 設定、バージョン、実行時パス
│   ├── persistence.py               # JSON アトミック永続化
│   ├── security.py                  # オリジン、セッション、アクセスキー検証
│   └── startup.py                   # 起動チェック（ポート占有 + 単一インスタンス検出）

run.py                               # 起動スクリプト（デュアルサービス）
pattern-generator.spec                # PyInstaller ビルド設定
requirements.txt                      # 依存関係リスト
```

## ディスカッションと交流

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;使用中に問題が発生した場合、または新機能のリクエスト・改善提案がある場合は、[GitHub Issues](https://github.com/MqKeYan/pattern-generator/issues) でお知らせください。解決方法があれば、Pull Request を送ってプロジェクトの改善にご協力いただけると大変嬉しいです！

## 行動規範

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本プロジェクトは [**Contributor Covenant Code of Conduct**](../CODE_OF_CONDUCT.md) に従います。オープンで友好的、相互尊重のあるコミュニティ環境の構築に努めています。

## ライセンス

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;本プロジェクトは **GPL-3.0 License** で提供されています。詳細は [LICENSE](../LICENSE) ファイルを参照してください。
