"""告警通知 - 系统弹窗、提示音、PushPlus 微信推送

- 按 settings.notifications.alert_events 过滤事件。
- 任一渠道失败静默降级，不影响主流程。
- 队列积压告警带恢复回滞：解除积压前不重复告警。
"""

import json
import threading
import time
import urllib.request
from collections import deque

EVENT_LABELS = {
    'task_failed': '任务失败',
    'queue_backlog': '队列积压',
    'gpu_overheat': 'GPU 过热',
    'task_timeout': '任务超时',
    'client_kicked': '客户端被踢出',
}

# 告警事件内存缓冲（报表数据源，重启清零）
_ALERT_BUFFER_SIZE = 200


class NotificationManager:
    def __init__(self, logger=None, settings=None):
        self.log = logger
        self.settings = settings or {}
        self._backlog_active = False
        self._lock = threading.Lock()
        self.alerts = deque(maxlen=_ALERT_BUFFER_SIZE)

    # ---------- 配置 ----------

    def _notify_config(self):
        cfg = self.settings.get('notifications', {})
        return {
            'toast': bool(cfg.get('system_toast', True)),
            'sound': bool(cfg.get('system_sound', True)),
            'pushplus': bool(cfg.get('pushplus_enabled', False)),
            'token': cfg.get('pushplus_token', ''),
            'topic': cfg.get('pushplus_topic', ''),
            'events': cfg.get('alert_events', []),
            'backlog_threshold': int(cfg.get('queue_backlog_threshold', 10)),
        }

    # ---------- 事件入口 ----------

    def notify(self, event_type, detail=''):
        """触发告警事件（event_type 需在 alert_events 中启用）"""
        cfg = self._notify_config()
        if event_type not in cfg['events']:
            return
        label = EVENT_LABELS.get(event_type, event_type)
        text = f'[{label}] {detail}' if detail else label
        text = text[:200]
        with self._lock:
            self.alerts.append({'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'event': event_type, 'detail': text})
        if self.log:
            self.log.warning(f'告警: {text}')
        if cfg['toast']:
            self._toast(label, text)
        if cfg['sound']:
            self._sound()
        if cfg['pushplus'] and cfg['token']:
            self._pushplus(cfg, label, text)

    def check_queue_backlog(self, waiting_count):
        """队列积压检查（回滞：恢复前不重复告警），由周期任务调用"""
        cfg = self._notify_config()
        if waiting_count > cfg['backlog_threshold']:
            if not self._backlog_active:
                with self._lock:
                    self._backlog_active = True
                self.notify('queue_backlog', f'等待任务数 {waiting_count} 超过阈值 {cfg["backlog_threshold"]}')
        elif self._backlog_active:
            with self._lock:
                self._backlog_active = False

    def notify_test(self):
        """测试推送：走全部启用渠道，不受 alert_events 过滤"""
        cfg = self._notify_config()
        text = '这是一条测试通知'
        if self.log:
            self.log.info('测试推送')
        if cfg['toast']:
            self._toast('测试通知', text)
        if cfg['sound']:
            self._sound()
        if cfg['pushplus'] and cfg['token']:
            self._pushplus(cfg, '测试通知', text)

    # ---------- 渠道 ----------

    def _toast(self, title, message):
        def worker():
            try:
                from plyer import notification
                notification.notify(title=f'斑图系统 · {title}', message=message, timeout=8)
            except Exception:
                pass  # 通知失败静默降级
        threading.Thread(target=worker, daemon=True).start()

    def _sound(self):
        def worker():
            try:
                import winsound
                for _ in range(2):
                    winsound.Beep(1200, 180)
                    winsound.Beep(800, 180)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _pushplus(self, cfg, title, content):
        def worker():
            body = json.dumps({
                'token': cfg['token'],
                'title': f'斑图系统 · {title}',
                'content': content,
                'template': 'txt',
                **({'topic': cfg['topic']} if cfg['topic'] else {}),
            }).encode('utf-8')
            for attempt in range(2):
                try:
                    req = urllib.request.Request(
                        'https://www.pushplus.plus/send', data=body,
                        headers={'Content-Type': 'application/json'})
                    urllib.request.urlopen(req, timeout=5)
                    return
                except Exception as exc:
                    if attempt == 1 and self.log:
                        # 不记录响应体和 token，避免凭据进入日志。
                        self.log.error(f'PushPlus 推送失败（已重试）: {type(exc).__name__}')
        threading.Thread(target=worker, daemon=True).start()
