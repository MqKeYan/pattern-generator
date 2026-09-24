"""日志系统 - 每次运行独立写入日志文件，并保留内存回放缓冲

- 文件按启动时间和 PID 命名，本地永久保留；每次运行独立成文件。
- 内存保留最近 1000 条，供新 WebSocket 连接回放。
- 日志格式：[时间] [级别] 消息
"""

import logging
import locale
import os
import re
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from common.config import software_root

SOFTWARE_ROOT = software_root()
LOG_DIR = SOFTWARE_ROOT / 'log'

_MEMORY_BUFFER_SIZE = 1000

_TASK_MODE_LABELS = {
    'simulate': '模拟',
    'animate': '动画',
}

_SUPPORTED_LOG_LANGUAGES = ('zh-CN', 'zh-TW', 'en', 'ja', 'ko')

_LOG_EVENTS = {
    'zh-CN': {
        'task_memory_release': '任务结果交付后内存回收', 'task_submit': '任务提交',
        'cache_clear_complete': '清理缓存完成', 'cache_clear_failed': '清理缓存失败',
        'cache_restore_complete': '恢复缓存完成', 'client_access_rejected': '客户端接入拒绝',
        'client_connected': '客户端接入', 'client_sweep_failed': '客户端离线清扫失败',
        'stats_persist_failed': '统计落盘失败', 'access_list_write_failed': '访问名单写入失败',
        'cache_result_write_failed': '结果缓存写入失败', 'cache_result_cleanup_failed': '结果缓存清理失败',
        'monitor_sample_failed': '监控采样失败', 'task_callback_failed': '任务事件回调异常',
        'task_queued': '任务入队', 'task_cancelled': '任务取消', 'task_cancel_requested': '任务取消请求',
        'task_dead_retry': '死信重试', 'task_dispatch_failed': '任务调度循环异常', 'task_timeout': '任务超时',
        'task_result_expired': '任务结果过期释放', 'task_started': '任务开始',
        'task_result_persist_failed': '任务结果落盘失败', 'task_result_memory_pending': '任务结果暂存内存等待领取',
        'task_result_release_failed': '任务结果内存回收失败', 'task_completed': '任务完成',
        'task_failed': '任务失败', 'task_retry': '任务重试', 'task_dead_letter': '任务进入死信',
        'client_pause': '客户端暂停', 'client_resume': '客户端恢复', 'client_kick': '客户端踢出',
        'client_cache_clear': '客户端缓存清理', 'client_record_delete': '客户端记录删除',
        'client_remark_update': '客户端备注更新', 'all_client_cache_clear': '全部客户端缓存清理',
        'all_client_stats_clear': '全部客户端统计清除', 'all_client_counter_reset': '全部客户端计数重置',
        'task_cancel_action': '任务取消操作', 'dead_task_retry': '死信任务重试',
        'dead_task_delete': '死信任务删除', 'all_tasks_interrupt': '全部任务中断',
        'queue_clear': '等待队列清空', 'access_control_update': '访问控制更新', 'report_export': '报表导出',
        'settings_update': '系统设置修改', 'settings_reset': '系统设置恢复默认',
        'service_shutdown_request': '全部服务停止请求', 'alert_triggered': '告警触发',
        'test_push': '测试推送', 'pushplus_failed': 'PushPlus 推送失败', 'notification_channel_failed': '通知渠道发送失败',
    },
    'zh-TW': {
        'task_memory_release': '任務結果交付後記憶體回收', 'task_submit': '任務提交',
        'cache_clear_complete': '清理快取完成', 'cache_clear_failed': '清理快取失敗',
        'cache_restore_complete': '恢復快取完成', 'client_access_rejected': '用戶端接入拒絕',
        'client_connected': '用戶端接入', 'client_sweep_failed': '用戶端離線清理失敗',
        'stats_persist_failed': '統計寫入失敗', 'access_list_write_failed': '存取名單寫入失敗',
        'cache_result_write_failed': '結果快取寫入失敗', 'cache_result_cleanup_failed': '結果快取清理失敗',
        'monitor_sample_failed': '監控取樣失敗', 'task_callback_failed': '任務事件回呼異常',
        'task_queued': '任務入列', 'task_cancelled': '任務取消', 'task_cancel_requested': '任務取消請求',
        'task_dead_retry': '死信重試', 'task_dispatch_failed': '任務調度迴圈異常', 'task_timeout': '任務逾時',
        'task_result_expired': '任務結果過期釋放', 'task_started': '任務開始',
        'task_result_persist_failed': '任務結果寫入失敗', 'task_result_memory_pending': '任務結果暫存記憶體等待領取',
        'task_result_release_failed': '任務結果記憶體回收失敗', 'task_completed': '任務完成',
        'task_failed': '任務失敗', 'task_retry': '任務重試', 'task_dead_letter': '任務進入死信',
        'client_pause': '用戶端暫停', 'client_resume': '用戶端恢復', 'client_kick': '用戶端踢出',
        'client_cache_clear': '用戶端快取清理', 'client_record_delete': '用戶端記錄刪除',
        'client_remark_update': '用戶端備註更新', 'all_client_cache_clear': '全部用戶端快取清理',
        'all_client_stats_clear': '全部用戶端統計清除', 'all_client_counter_reset': '全部用戶端計數重設',
        'task_cancel_action': '任務取消操作', 'dead_task_retry': '死信任務重試',
        'dead_task_delete': '死信任務刪除', 'all_tasks_interrupt': '全部任務中斷',
        'queue_clear': '等待佇列清空', 'access_control_update': '存取控制更新', 'report_export': '報表匯出',
        'settings_update': '系統設定修改', 'settings_reset': '系統設定恢復預設',
        'service_shutdown_request': '全部服務停止請求', 'alert_triggered': '警告觸發',
        'test_push': '測試推送', 'pushplus_failed': 'PushPlus 推送失敗', 'notification_channel_failed': '通知渠道發送失敗',
    },
    'en': {
        'task_memory_release': 'Task Result Memory Release', 'task_submit': 'Task Submitted',
        'cache_clear_complete': 'Cache Clear Completed', 'cache_clear_failed': 'Cache Clear Failed',
        'cache_restore_complete': 'Cache Restore Completed', 'client_access_rejected': 'Client Access Rejected',
        'client_connected': 'Client Connected', 'client_sweep_failed': 'Client Offline Sweep Failed',
        'stats_persist_failed': 'Statistics Save Failed', 'access_list_write_failed': 'Access List Write Failed',
        'cache_result_write_failed': 'Result Cache Write Failed', 'cache_result_cleanup_failed': 'Result Cache Cleanup Failed',
        'monitor_sample_failed': 'Monitor Sampling Failed', 'task_callback_failed': 'Task Event Callback Failed',
        'task_queued': 'Task Queued', 'task_cancelled': 'Task Cancelled', 'task_cancel_requested': 'Task Cancellation Requested',
        'task_dead_retry': 'Dead Task Retried', 'task_dispatch_failed': 'Task Dispatch Loop Failed', 'task_timeout': 'Task Timed Out',
        'task_result_expired': 'Task Result Expired', 'task_started': 'Task Started',
        'task_result_persist_failed': 'Task Result Save Failed', 'task_result_memory_pending': 'Task Result Kept In Memory',
        'task_result_release_failed': 'Task Result Memory Release Failed', 'task_completed': 'Task Completed',
        'task_failed': 'Task Failed', 'task_retry': 'Task Retried', 'task_dead_letter': 'Task Moved To Dead Letter',
        'client_pause': 'Client Paused', 'client_resume': 'Client Resumed', 'client_kick': 'Client Kicked',
        'client_cache_clear': 'Client Cache Cleared', 'client_record_delete': 'Client Record Deleted',
        'client_remark_update': 'Client Remark Updated', 'all_client_cache_clear': 'All Client Caches Cleared',
        'all_client_stats_clear': 'All Client Statistics Cleared', 'all_client_counter_reset': 'All Client Counters Reset',
        'task_cancel_action': 'Task Cancellation Action', 'dead_task_retry': 'Dead Task Retried',
        'dead_task_delete': 'Dead Task Deleted', 'all_tasks_interrupt': 'All Tasks Interrupted',
        'queue_clear': 'Waiting Queue Cleared', 'access_control_update': 'Access Control Updated', 'report_export': 'Report Exported',
        'settings_update': 'System Settings Updated', 'settings_reset': 'System Settings Reset',
        'service_shutdown_request': 'Service Shutdown Requested', 'alert_triggered': 'Alert Triggered',
        'test_push': 'Test Push', 'pushplus_failed': 'PushPlus Push Failed', 'notification_channel_failed': 'Notification Channel Failed',
    },
    'ja': {
        'task_memory_release': 'タスク結果メモリ解放', 'task_submit': 'タスク送信',
        'cache_clear_complete': 'キャッシュ消去完了', 'cache_clear_failed': 'キャッシュ消去失敗',
        'cache_restore_complete': 'キャッシュ復元完了', 'client_access_rejected': 'クライアント接続拒否',
        'client_connected': 'クライアント接続', 'client_sweep_failed': 'オフラインクライアント整理失敗',
        'stats_persist_failed': '統計保存失敗', 'access_list_write_failed': 'アクセスリスト書込失敗',
        'cache_result_write_failed': '結果キャッシュ書込失敗', 'cache_result_cleanup_failed': '結果キャッシュ整理失敗',
        'monitor_sample_failed': 'モニターサンプリング失敗', 'task_callback_failed': 'タスクイベントコールバック失敗',
        'task_queued': 'タスクキュー追加', 'task_cancelled': 'タスク取消', 'task_cancel_requested': 'タスク取消要求',
        'task_dead_retry': 'デッドタスク再試行', 'task_dispatch_failed': 'タスク配信ループ失敗', 'task_timeout': 'タスクタイムアウト',
        'task_result_expired': 'タスク結果期限切れ解放', 'task_started': 'タスク開始',
        'task_result_persist_failed': 'タスク結果保存失敗', 'task_result_memory_pending': 'タスク結果をメモリに保持',
        'task_result_release_failed': 'タスク結果メモリ解放失敗', 'task_completed': 'タスク完了',
        'task_failed': 'タスク失敗', 'task_retry': 'タスク再試行', 'task_dead_letter': 'タスクをデッドレターへ移動',
        'client_pause': 'クライアント一時停止', 'client_resume': 'クライアント再開', 'client_kick': 'クライアント退出',
        'client_cache_clear': 'クライアントキャッシュ消去', 'client_record_delete': 'クライアント記録削除',
        'client_remark_update': 'クライアント備考更新', 'all_client_cache_clear': '全クライアントキャッシュ消去',
        'all_client_stats_clear': '全クライアント統計消去', 'all_client_counter_reset': '全クライアントカウンターリセット',
        'task_cancel_action': 'タスク取消操作', 'dead_task_retry': 'デッドタスク再試行',
        'dead_task_delete': 'デッドタスク削除', 'all_tasks_interrupt': '全タスク中断',
        'queue_clear': '待機キュー消去', 'access_control_update': 'アクセス制御更新', 'report_export': 'レポート出力',
        'settings_update': 'システム設定変更', 'settings_reset': 'システム設定初期化',
        'service_shutdown_request': '全サービス停止要求', 'alert_triggered': 'アラート発生',
        'test_push': 'テスト通知', 'pushplus_failed': 'PushPlus送信失敗', 'notification_channel_failed': '通知チャネル送信失敗',
    },
    'ko': {
        'task_memory_release': '작업 결과 메모리 해제', 'task_submit': '작업 제출',
        'cache_clear_complete': '캐시 정리 완료', 'cache_clear_failed': '캐시 정리 실패',
        'cache_restore_complete': '캐시 복원 완료', 'client_access_rejected': '클라이언트 접속 거부',
        'client_connected': '클라이언트 접속', 'client_sweep_failed': '오프라인 클라이언트 정리 실패',
        'stats_persist_failed': '통계 저장 실패', 'access_list_write_failed': '접근 목록 저장 실패',
        'cache_result_write_failed': '결과 캐시 저장 실패', 'cache_result_cleanup_failed': '결과 캐시 정리 실패',
        'monitor_sample_failed': '모니터 샘플링 실패', 'task_callback_failed': '작업 이벤트 콜백 실패',
        'task_queued': '작업 대기열 등록', 'task_cancelled': '작업 취소', 'task_cancel_requested': '작업 취소 요청',
        'task_dead_retry': '실패 작업 재시도', 'task_dispatch_failed': '작업 디스패치 루프 실패', 'task_timeout': '작업 시간 초과',
        'task_result_expired': '작업 결과 만료 해제', 'task_started': '작업 시작',
        'task_result_persist_failed': '작업 결과 저장 실패', 'task_result_memory_pending': '작업 결과 메모리 보관',
        'task_result_release_failed': '작업 결과 메모리 해제 실패', 'task_completed': '작업 완료',
        'task_failed': '작업 실패', 'task_retry': '작업 재시도', 'task_dead_letter': '작업을 실패 대기열로 이동',
        'client_pause': '클라이언트 일시 중지', 'client_resume': '클라이언트 재개', 'client_kick': '클라이언트 퇴출',
        'client_cache_clear': '클라이언트 캐시 정리', 'client_record_delete': '클라이언트 기록 삭제',
        'client_remark_update': '클라이언트 메모 수정', 'all_client_cache_clear': '전체 클라이언트 캐시 정리',
        'all_client_stats_clear': '전체 클라이언트 통계 삭제', 'all_client_counter_reset': '전체 클라이언트 카운터 초기화',
        'task_cancel_action': '작업 취소 작업', 'dead_task_retry': '실패 작업 재시도',
        'dead_task_delete': '실패 작업 삭제', 'all_tasks_interrupt': '전체 작업 중단',
        'queue_clear': '대기열 비우기', 'access_control_update': '접근 제어 업데이트', 'report_export': '보고서 내보내기',
        'settings_update': '시스템 설정 수정', 'settings_reset': '시스템 설정 초기화',
        'service_shutdown_request': '전체 서비스 종료 요청', 'alert_triggered': '경고 발생',
        'test_push': '테스트 알림', 'pushplus_failed': 'PushPlus 전송 실패', 'notification_channel_failed': '알림 채널 전송 실패',
    },
}

_LOG_LABELS = {
    'zh-CN': {'client': '客户端', 'model': '模型'},
    'zh-TW': {'client': '用戶端', 'model': '模型'},
    'en': {'client': 'Client', 'model': 'Model'},
    'ja': {'client': 'クライアント', 'model': 'モデル'},
    'ko': {'client': '클라이언트', 'model': '모델'},
}

_SEGMENT_TRANSLATIONS = {
    'zh-CN': {'模拟': '模拟', '动画': '动画', 'GPU': 'GPU'},
    'zh-TW': {'模拟': '模擬', '动画': '動畫', 'GPU': 'GPU'},
    'en': {'模拟': 'Simulation', '动画': 'Animation', 'GPU': 'GPU'},
    'ja': {'模拟': 'シミュレーション', '动画': 'アニメーション', 'GPU': 'GPU'},
    'ko': {'模拟': '시뮬레이션', '动画': '애니메이션', 'GPU': 'GPU'},
}

_LOG_PUNCTUATION = {
    'zh-CN': ('：', '，'),
    'zh-TW': ('：', '，'),
    'en': (': ', ', '),
    'ja': ('：', '、'),
    'ko': ('：', ', '),
}

_BRIEF_FAILURE_REASONS = {
    'zh-CN': {'label': '原因', 'gpu_memory': '显存不足', 'memory': '内存不足', 'disk': '磁盘空间不足', 'permission': '权限不足', 'timeout': '超时'},
    'zh-TW': {'label': '原因', 'gpu_memory': '顯示記憶體不足', 'memory': '記憶體不足', 'disk': '磁碟空間不足', 'permission': '權限不足', 'timeout': '逾時'},
    'en': {'label': 'Cause', 'gpu_memory': 'GPU memory exhausted', 'memory': 'Memory exhausted', 'disk': 'Disk full', 'permission': 'Permission denied', 'timeout': 'Timed out'},
    'ja': {'label': '原因', 'gpu_memory': 'GPUメモリ不足', 'memory': 'メモリ不足', 'disk': 'ディスク容量不足', 'permission': '権限不足', 'timeout': 'タイムアウト'},
    'ko': {'label': '원인', 'gpu_memory': 'GPU 메모리 부족', 'memory': '메모리 부족', 'disk': '디스크 공간 부족', 'permission': '권한 부족', 'timeout': '시간 초과'},
}

_MODEL_RE = re.compile(r'^模型(\d+)$')


def detect_log_language():
    """读取操作系统语言，作为服务启动时的统一日志语言。"""
    candidates = []
    try:
        candidates.append(locale.getlocale()[0])
    except (ValueError, TypeError):
        pass
    candidates.extend((os.environ.get('LANG'), os.environ.get('LANGUAGE')))
    for value in candidates:
        value = str(value or '').lower()
        if value.startswith('zh_tw') or value.startswith('zh_hk') or value.startswith('zh_mo'):
            return 'zh-TW'
        if value.startswith('zh'):
            return 'zh-CN'
        if value.startswith('ja'):
            return 'ja'
        if value.startswith('ko'):
            return 'ko'
        if value:
            return 'en'
    return 'zh-CN'


def normalize_log_language(language):
    return language if language in _SUPPORTED_LOG_LANGUAGES else 'zh-CN'


def task_mode_label(task_type):
    """将任务类型转换为统一中文日志标签。"""
    value = str(task_type or '').strip()
    return _TASK_MODE_LABELS.get(value, value or '未知')


def _localize_segment(segment, language):
    value = str(segment or '').strip()
    if not value:
        return ''
    model_match = _MODEL_RE.fullmatch(value)
    if model_match:
        return f"{_LOG_LABELS[language]['model']}{model_match.group(1)}"
    return _SEGMENT_TRANSLATIONS[language].get(value, value)


def _brief_failure_reason(detail, language):
    """只提取可本地化的常见失败原因，不输出底层异常原文。"""
    if not isinstance(detail, dict):
        return ''
    raw = detail.get('error') or detail.get('reason') or detail.get('exception')
    text = str(raw or '').lower()
    if not text:
        return ''
    if 'out of memory' in text or '显存不足' in text or '顯示記憶體不足' in text:
        kind = 'gpu_memory' if any(word in text for word in ('cuda', 'gpu', '显存', '顯示記憶體')) else 'memory'
    elif 'no space left' in text or '磁盘空间不足' in text or '磁碟空間不足' in text:
        kind = 'disk'
    elif 'permission denied' in text or '权限不足' in text or '權限不足' in text:
        kind = 'permission'
    elif 'timed out' in text or 'timeout' in text or '超时' in text or '逾時' in text:
        kind = 'timeout'
    else:
        return ''
    return _BRIEF_FAILURE_REASONS[language][kind]


def format_event(action, *segments, client_id=None, task_id=None, target=None,
                 source='系统', detail=None, client_name=None, language='zh-CN', level=logging.INFO):
    """构造简短日志正文，不拼接任务编号和常规详情。"""
    language = normalize_log_language(language)
    left_parts = [_LOG_EVENTS[language].get(action, str(action or '').strip())]
    left_parts.extend(_localize_segment(segment, language) for segment in segments if str(segment or '').strip())
    left = '-'.join(left_parts)

    context = []
    if client_id:
        context.append(f"{_LOG_LABELS[language]['client']}{client_id}")
    if level >= logging.WARNING:
        reason = _brief_failure_reason(detail, language)
        if reason:
            context.append(f"{_BRIEF_FAILURE_REASONS[language]['label']}{reason}")
    colon, comma = _LOG_PUNCTUATION[language]
    return f"{left}{colon if context else ''}{comma.join(context)}".replace(' ', '')


class _MemoryBufferHandler(logging.Handler):
    """保留最近 N 条格式化日志，带自增序号供增量拉取"""

    def __init__(self, capacity):
        super().__init__()
        # 注意：Handler 自带 self.lock（handle() 调 emit() 前已持有），
        # 缓冲区必须用独立命名的锁，避免非重入死锁
        self._buf_lock = threading.Lock()
        self.buffer = deque(maxlen=capacity)
        self.seq = 0

    def emit(self, record):
        try:
            msg = self.format(record)
            with self._buf_lock:
                self.seq += 1
                self.buffer.append({
                    'seq': self.seq,
                    'message': msg,
                    'client_id': getattr(record, 'client_id', ''),
                    'task_id': getattr(record, 'task_id', ''),
                    'action': getattr(record, 'log_action', ''),
                })
        except Exception:
            self.handleError(record)

    def replay(self, since_seq=0):
        with self._buf_lock:
            return [entry for entry in self.buffer if entry['seq'] > since_seq]


class _RunFileHandler(logging.Handler):
    """为每次软件运行创建独立日志文件（线程安全）。"""

    def __init__(self, log_dir):
        super().__init__()
        self.log_dir = Path(log_dir)
        self._lock = threading.Lock()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        pid = os.getpid()
        self.path = self.log_dir / f'{stamp}_{pid}.log'
        suffix = 1
        while self.path.exists():
            self.path = self.log_dir / f'{stamp}_{pid}_{suffix}.log'
            suffix += 1
        self._file = None

    def emit(self, record):
        try:
            msg = self.format(record)
            with self._lock:
                # 部分运行环境会提前关闭 logging 句柄，服务仍在运行时应恢复写入。
                if self._file is None or self._file.closed:
                    self._file = open(self.path, 'a', encoding='utf-8')
                self._file.write(msg + '\n')
                self._file.flush()
        except Exception:
            self.handleError(record)

    def current_file(self):
        with self._lock:
            return str(self.path)

    def close(self):
        with self._lock:
            try:
                if self._file is not None:
                    self._file.close()
            except OSError:
                pass


class SystemLogger:
    """系统日志器：stderr + 日期文件 + 内存回放缓冲"""

    def __init__(self, name='pattern', log_dir=LOG_DIR):
        self._language_lock = threading.Lock()
        self._language = detect_log_language()
        self._language_locked = False
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if self.logger.handlers:
            return  # 已初始化（模块重载保护）

        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        console = logging.StreamHandler(stream=sys.stderr)
        console.setFormatter(formatter)
        self.logger.addHandler(console)

        self.file_handler = _RunFileHandler(log_dir)
        self.file_handler.setFormatter(formatter)
        self.logger.addHandler(self.file_handler)

        self.memory_handler = _MemoryBufferHandler(_MEMORY_BUFFER_SIZE)
        self.memory_handler.setFormatter(formatter)
        self.logger.addHandler(self.memory_handler)

    def set_language(self, language):
        """设置本次运行的统一日志语言，首条日志写入后不再切换，避免历史日志混合。"""
        language = normalize_log_language(language)
        with self._language_lock:
            if not self._language_locked:
                self._language = language

    def get_language(self):
        with self._language_lock:
            return self._language

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def audit(self, message):
        """后台管理操作审计日志"""
        self.logger.info(f'[审计] {message}')

    def event(self, level, action, *segments, client_id=None, task_id=None,
              target=None, source='系统', detail=None, client_name=None, exc_info=False):
        """按统一字段模板写入日志事件。"""
        with self._language_lock:
            self._language_locked = True
            language = self._language
        message = format_event(
            action,
            *segments,
            client_id=client_id,
            task_id=task_id,
            target=target,
            source=source,
            detail=detail,
            client_name=client_name,
            language=language,
            level=level,
        )
        self.logger.log(
            level,
            message,
            exc_info=exc_info,
            extra={
                'client_id': str(client_id or ''),
                'task_id': str(task_id or ''),
                'log_action': str(action or ''),
            },
        )

    def info_event(self, action, *segments, **kwargs):
        self.event(logging.INFO, action, *segments, **kwargs)

    def warning_event(self, action, *segments, **kwargs):
        self.event(logging.WARNING, action, *segments, **kwargs)

    def error_event(self, action, *segments, **kwargs):
        self.event(logging.ERROR, action, *segments, **kwargs)

    def audit_event(self, action, *segments, **kwargs):
        """后台操作审计事件，使用与业务日志相同的字段模板。"""
        kwargs.setdefault('source', '后台管理员')
        self.event(logging.INFO, action, *segments, **kwargs)

    def replay(self, since_seq=0):
        """回放内存缓冲中的日志（seq 之后的条目）"""
        return self.memory_handler.replay(since_seq)

    def current_file(self):
        return self.file_handler.current_file()

    def shutdown(self):
        for handler in list(self.logger.handlers):
            try:
                handler.close()
            except Exception:
                pass
            self.logger.removeHandler(handler)


_logger = None


def get_logger():
    """获取全局日志器单例"""
    global _logger
    if _logger is None:
        _logger = SystemLogger()
    return _logger
