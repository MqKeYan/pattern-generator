"""本地 JSON 文件的安全读写辅助函数。"""

import json
import locale
import os
import re
import shutil
import sys
import threading
import time
import uuid
from functools import lru_cache
from pathlib import Path


_WRITE_LOCK = threading.RLock()

# JSON 标准不允许 // 注释。_说明 是不参与业务设置的结构化注释。
# 顺序和网页现有语言一致；系统不支持的语言回退英语。
_CONFIG_NOTES = {
    'zh-CN': {
        'startup.json': ('启动与服务设置', 'port：主服务端口；admin_port：后台端口；auto_open_browser、auto_open_admin_browser：启动时是否打开浏览器。'),
        'compute.json': ('全局计算设置', 'compute_engine：计算引擎；compute_device：计算设备；compute_python：外部 Python 路径，auto 表示软件自动选择。'),
        'monitor.json': ('监控设置', 'monitor_default_view：默认视图；metrics_window_seconds：监控曲线的时间窗口。'),
        'tasks.json': ('任务与缓存设置', 'task_timeout_seconds：任务超时；task_retry_count：失败重试次数；其他字段控制结果保留、队列容量与显存预留。并发数由启动时自动识别。'),
        'access.json': ('访问控制设置', 'allowed_hosts：允许的主机；request_rate_limit、request_rate_window_seconds：请求限流；其他字段限制客户端和连接数量。'),
        'notifications.json': ('告警通知设置', 'notifications：通知渠道、目标、凭据、事件及阈值；可能包含敏感信息，请勿公开。'),
        'blacklist.json': ('访问黑名单', 'ips：被拒绝的 IP 或网段；client_ids：被拒绝的客户端 ID。'),
        'whitelist.json': ('访问白名单', 'ips：允许的 IP 或网段；client_ids：允许的客户端 ID。'),
        'compute-engine-state.json': ('计算引擎启动状态', 'engine：上次实际使用的引擎；手动选择以 compute.json 为准。'),
        'compute-python-state.json': ('Python 启动页面状态', 'version：状态格式版本；手动选择以 compute.json 为准。'),
        'stats.json': ('客户端与资源统计', 'saved_at：保存时间；peaks：资源峰值；clients：客户端累计统计与备注。'),
        'misc.json': ('旧版扩展设置', '迁移时保留无法归入现有功能文件的旧版扩展字段。'),
        'instance.lock': ('运行实例锁', 'pid：进程号；port、admin_port：占用的端口；正常退出时移除。'),
    },
    'zh-TW': {
        'startup.json': ('啟動與服務設定', 'port：主服務埠；admin_port：後台埠；auto_open_browser、auto_open_admin_browser：啟動時是否開啟瀏覽器。'),
        'compute.json': ('全域運算設定', 'compute_engine：運算引擎；compute_device：運算裝置；compute_python：外部 Python 路徑；auto 代表自動選擇。'),
        'monitor.json': ('監控設定', 'monitor_default_view：預設檢視；metrics_window_seconds：監控曲線時間範圍。'),
        'tasks.json': ('任務與快取設定', 'task_timeout_seconds：逾時；task_retry_count：重試次數；其餘欄位控制結果保留、佇列與顯示記憶體預留。並行數於啟動時自動偵測。'),
        'access.json': ('存取控制設定', 'allowed_hosts：允許的主機；request_rate_limit、request_rate_window_seconds：請求速率限制；其餘欄位限制用戶端及連線數。'),
        'notifications.json': ('警示通知設定', 'notifications：通知管道、目標、憑證、事件與門檻；可能含敏感資料，請勿公開。'),
        'blacklist.json': ('存取黑名單', 'ips：拒絕的 IP 或網段；client_ids：拒絕的用戶端 ID。'),
        'whitelist.json': ('存取白名單', 'ips：允許的 IP 或網段；client_ids：允許的用戶端 ID。'),
        'compute-engine-state.json': ('運算引擎啟動狀態', 'engine：上次實際使用的引擎；手動選擇以 compute.json 為準。'),
        'compute-python-state.json': ('Python 啟動頁面狀態', 'version：狀態格式版本；手動選擇以 compute.json 為準。'),
        'stats.json': ('用戶端與資源統計', 'saved_at：儲存時間；peaks：資源峰值；clients：用戶端累計統計與備註。'),
        'misc.json': ('舊版擴充設定', '遷移時保留無法歸入現有功能檔案的舊版擴充欄位。'),
        'instance.lock': ('執行個體鎖', 'pid：行程 ID；port、admin_port：使用中的埠；正常結束時移除。'),
    },
    'en': {
        'startup.json': ('Startup and service settings', 'port: main port; admin_port: admin port; auto_open_browser and auto_open_admin_browser: open browsers at startup.'),
        'compute.json': ('Global compute settings', 'compute_engine: engine; compute_device: device; compute_python: external Python path; auto selects automatically.'),
        'monitor.json': ('Monitoring settings', 'monitor_default_view: default view; metrics_window_seconds: chart time window.'),
        'tasks.json': ('Task and cache settings', 'task_timeout_seconds: timeout; task_retry_count: retries; other fields control result retention, queue limits, and reserved GPU memory. Concurrency is detected at startup.'),
        'access.json': ('Access control settings', 'allowed_hosts: allowed hosts; request_rate_limit and request_rate_window_seconds: rate limit; other fields limit clients and connections.'),
        'notifications.json': ('Alert settings', 'notifications: channels, targets, credentials, events, and thresholds. May contain secrets; do not share.'),
        'blacklist.json': ('Access blacklist', 'ips: blocked IPs or subnets; client_ids: blocked client IDs.'),
        'whitelist.json': ('Access whitelist', 'ips: allowed IPs or subnets; client_ids: allowed client IDs.'),
        'compute-engine-state.json': ('Compute engine startup state', 'engine: last engine used; manual selection is stored in compute.json.'),
        'compute-python-state.json': ('Python startup page state', 'version: state format version; manual selection is stored in compute.json.'),
        'stats.json': ('Client and resource statistics', 'saved_at: save time; peaks: resource peaks; clients: cumulative client statistics and notes.'),
        'misc.json': ('Legacy extension settings', 'Preserves legacy fields that do not belong to a current feature file.'),
        'instance.lock': ('Running instance lock', 'pid: process ID; port and admin_port: occupied ports; removed on normal exit.'),
    },
    'ja': {
        'startup.json': ('起動とサービスの設定', 'port：メインポート；admin_port：管理ポート；auto_open_browser と auto_open_admin_browser：起動時にブラウザーを開く設定。'),
        'compute.json': ('共通計算設定', 'compute_engine：計算エンジン；compute_device：計算デバイス；compute_python：外部 Python のパス；auto は自動選択。'),
        'monitor.json': ('監視設定', 'monitor_default_view：既定の表示；metrics_window_seconds：グラフの時間範囲。'),
        'tasks.json': ('タスクとキャッシュの設定', 'task_timeout_seconds：タイムアウト；task_retry_count：再試行回数；その他の項目は結果の保存期間、キュー、GPU メモリ予約を制御。並列数は起動時に検出。'),
        'access.json': ('アクセス制御設定', 'allowed_hosts：許可するホスト；request_rate_limit と request_rate_window_seconds：リクエスト制限；その他の項目はクライアントと接続数を制限。'),
        'notifications.json': ('警告通知設定', 'notifications：通知先、認証情報、イベント、しきい値。機密情報を含む場合があるため公開しないでください。'),
        'blacklist.json': ('アクセス拒否リスト', 'ips：拒否する IP またはサブネット；client_ids：拒否するクライアント ID。'),
        'whitelist.json': ('アクセス許可リスト', 'ips：許可する IP またはサブネット；client_ids：許可するクライアント ID。'),
        'compute-engine-state.json': ('計算エンジンの起動状態', 'engine：前回使用したエンジン；手動選択は compute.json を参照。'),
        'compute-python-state.json': ('Python 起動画面の状態', 'version：状態形式のバージョン；手動選択は compute.json を参照。'),
        'stats.json': ('クライアントとリソースの統計', 'saved_at：保存日時；peaks：リソースの最大値；clients：クライアントの累積統計とメモ。'),
        'misc.json': ('旧版の拡張設定', '現在の機能別ファイルに分類できない旧版の項目を保持します。'),
        'instance.lock': ('実行中インスタンスのロック', 'pid：プロセス ID；port と admin_port：使用中のポート；正常終了時に削除。'),
    },
    'ko': {
        'startup.json': ('시작 및 서비스 설정', 'port: 주 서비스 포트; admin_port: 관리자 포트; auto_open_browser와 auto_open_admin_browser: 시작 시 브라우저 열기.'),
        'compute.json': ('전역 계산 설정', 'compute_engine: 계산 엔진; compute_device: 장치; compute_python: 외부 Python 경로; auto는 자동 선택.'),
        'monitor.json': ('모니터링 설정', 'monitor_default_view: 기본 보기; metrics_window_seconds: 그래프 시간 범위.'),
        'tasks.json': ('작업 및 캐시 설정', 'task_timeout_seconds: 제한 시간; task_retry_count: 재시도 횟수; 나머지 항목은 결과 보관, 대기열 및 GPU 메모리 예약을 제어. 동시 실행 수는 시작 시 감지.'),
        'access.json': ('접근 제어 설정', 'allowed_hosts: 허용 호스트; request_rate_limit와 request_rate_window_seconds: 요청 제한; 나머지 항목은 클라이언트와 연결 수를 제한.'),
        'notifications.json': ('경고 알림 설정', 'notifications: 알림 채널, 대상, 자격 증명, 이벤트 및 임계값. 민감한 정보가 포함될 수 있으므로 공유하지 마세요.'),
        'blacklist.json': ('접근 차단 목록', 'ips: 차단할 IP 또는 서브넷; client_ids: 차단할 클라이언트 ID.'),
        'whitelist.json': ('접근 허용 목록', 'ips: 허용할 IP 또는 서브넷; client_ids: 허용할 클라이언트 ID.'),
        'compute-engine-state.json': ('계산 엔진 시작 상태', 'engine: 마지막으로 사용한 엔진; 수동 선택은 compute.json에 저장.'),
        'compute-python-state.json': ('Python 시작 화면 상태', 'version: 상태 형식 버전; 수동 선택은 compute.json에 저장.'),
        'stats.json': ('클라이언트 및 자원 통계', 'saved_at: 저장 시각; peaks: 자원 최대값; clients: 클라이언트 누적 통계와 메모.'),
        'misc.json': ('이전 버전 확장 설정', '현재 기능별 파일에 속하지 않는 이전 버전의 확장 항목을 보존합니다.'),
        'instance.lock': ('실행 인스턴스 잠금', 'pid: 프로세스 ID; port와 admin_port: 사용 중인 포트; 정상 종료 시 제거.'),
    },
}


def _supported_note_language(language):
    """把系统区域设置映射到软件支持的五种说明语言。"""
    language = str(language).replace('_', '-').lower()
    if language.startswith('chinese'):
        return 'zh-TW' if any(word in language for word in (
            'traditional', 'taiwan', 'hong kong', 'macao')) else 'zh-CN'
    if language.startswith('zh-') and any(part in ('hant', 'tw', 'hk', 'mo')
                                              for part in language[3:].split('-')):
        return 'zh-TW'
    if language.startswith('zh'):
        return 'zh-CN'
    if language.startswith('ja'):
        return 'ja'
    if language.startswith('ko'):
        return 'ko'
    return 'en'


@lru_cache(maxsize=1)
def _system_note_language():
    """使用操作系统界面语言，不读取浏览器或软件内的语言偏好。"""
    language = None
    if sys.platform == 'win32':
        try:
            import ctypes
            language = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        except (AttributeError, OSError, ValueError):
            pass
    if not language:
        language = locale.getlocale()[0] or os.environ.get('LANG', '')
    return _supported_note_language(language)


def documented_config_object(path, data):
    """只给 config/ 中现用的 JSON/锁文件加入业务读取可忽略的说明。"""
    path = Path(path)
    if path.parent.name != 'config' or not isinstance(data, dict):
        return data
    language = _system_note_language()
    note = _CONFIG_NOTES[language].get(path.name)
    if note is None:
        return data
    return {'_说明': {'语言': language, '用途': note[0], '字段': note[1]},
            **{key: value for key, value in data.items() if key != '_说明'}}


def _has_current_note_prefix(path, expected):
    """只读文件头判断说明是否完整，避免每次启动解析大型统计文件。"""
    with path.open('r', encoding='utf-8') as handle:
        prefix = handle.read(2048)
    match = re.match(r'\s*\{\s*"_说明"\s*:\s*', prefix)
    if not match:
        return False
    try:
        note, _ = json.JSONDecoder().raw_decode(prefix, match.end())
    except ValueError:
        return False
    return note == expected


def ensure_config_comments(config_dir, skip=()):
    """每次启动仅检查文件头，缺失或不完整时才读取并修复全文件。"""
    config_dir = Path(config_dir)
    language = _system_note_language()
    for name, (purpose, fields) in _CONFIG_NOTES[language].items():
        if name == 'instance.lock' or name in skip:
            continue  # 锁由所属进程写入；功能文件已在 load_settings 中校验。
        path = config_dir / name
        if not path.is_file():
            continue
        expected = {'语言': language, '用途': purpose, '字段': fields}
        try:
            if _has_current_note_prefix(path, expected):
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue  # 各文件的业务读取路径负责损坏文件的处理。
        if isinstance(data, dict):
            try:
                atomic_write_json(path, data)
            except OSError:
                pass  # 注释修复失败不能妨碍启动；下次启动再尝试。


def atomic_write_json(path, data):
    """同目录临时文件写入并原子替换，避免中断留下半个 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    encoded = json.dumps(documented_config_object(path, data), ensure_ascii=False,
                         indent=2).encode('utf-8')
    with _WRITE_LOCK:
        try:
            with open(temp, 'wb') as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def backup_corrupt_file(path):
    """为无法解析的旧文件保留带时间戳副本。"""
    path = Path(path)
    if not path.is_file():
        return None
    backup = path.with_name(f'{path.stem}.bad-{time.strftime("%Y%m%d-%H%M%S")}{path.suffix}')
    try:
        shutil.copy2(path, backup)
        return backup
    except OSError:
        return None
