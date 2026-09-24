"""告警通知 - 系统弹窗、提示音、PushPlus 微信推送

- 按 settings.notifications.alert_events 过滤事件。
- 任一渠道失败静默降级，不影响主流程。
- 队列积压告警带恢复回滞：解除积压前不重复告警。
"""

import json
import re
import threading
import time
import urllib.request
from collections import deque
from common.notification_channels import sanitize_channel_targets, sanitize_pushplus_targets, send_channel_notifications

EVENT_LABELS = {
    'queue_backlog': '队列积压',
    'gpu_overheat': 'GPU 过热',
    'cpu_overload': 'CPU 负载过高',
    'memory_pressure': '内存压力过高',
    'swap_pressure': '交换区压力过高',
    'disk_space_low': '磁盘空间不足',
    'gpu_memory_pressure': 'GPU 显存压力过高',
    'gpu_power_high': 'GPU 功耗偏高',
    'cpu_power_high': 'CPU 功耗偏高',
    'client_kicked': '客户端被踢出',
}

CLIENT_TASK_TEXT = {
    'zh-CN': {
        'completed': ('任务完成', '{model} 已完成计算。'),
        'failed': ('任务失败', '{model} 计算失败。'),
        'cancelled': ('任务取消', '{model} 已取消。'),
        'timeout': ('任务超时', '{model} 已超时。'),
    },
    'zh-TW': {
        'completed': ('任務完成', '{model} 已完成計算。'),
        'failed': ('任務失敗', '{model} 計算失敗。'),
        'cancelled': ('任務取消', '{model} 已取消。'),
        'timeout': ('任務逾時', '{model} 已逾時。'),
    },
    'en': {
        'completed': ('Task Completed', '{model} has completed.'),
        'failed': ('Task Failed', '{model} has failed.'),
        'cancelled': ('Task Cancelled', '{model} was cancelled.'),
        'timeout': ('Task Timed Out', '{model} timed out.'),
    },
    'ja': {
        'completed': ('タスク完了', '{model} の計算が完了しました。'),
        'failed': ('タスク失敗', '{model} の計算に失敗しました。'),
        'cancelled': ('タスク取消', '{model} は取り消されました。'),
        'timeout': ('タスクタイムアウト', '{model} はタイムアウトしました。'),
    },
    'ko': {
        'completed': ('작업 완료', '{model} 계산이 완료되었습니다.'),
        'failed': ('작업 실패', '{model} 계산에 실패했습니다.'),
        'cancelled': ('작업 취소', '{model} 작업이 취소되었습니다.'),
        'timeout': ('작업 시간 초과', '{model} 작업 시간이 초과되었습니다.'),
    },
}

_MODEL_PREFIXES = {'zh-CN': '模型', 'zh-TW': '模型', 'en': 'Model', 'ja': 'モデル', 'ko': '모델'}


def _client_task_model_label(model, language):
    match = re.fullmatch(r'模型(\d+)', str(model or ''))
    return f'{_MODEL_PREFIXES[language]}{match.group(1)}' if match else str(model or '')

# 告警事件内存缓冲（报表数据源，重启清零）
_ALERT_BUFFER_SIZE = 200


class NotificationManager:
    def __init__(self, logger=None, settings=None):
        self.log = logger
        self.settings = settings or {}
        self._backlog_active = False
        self._threshold_states = {}
        self._lock = threading.Lock()
        self.alerts = deque(maxlen=_ALERT_BUFFER_SIZE)

    # ---------- 配置 ----------

    def _notify_config(self):
        cfg = self.settings.get('notifications', {})
        return {
            'toast': bool(cfg.get('system_toast', True)),
            'sound': bool(cfg.get('system_sound', True)),
            'pushplus_targets': self._pushplus_targets(cfg),
            'channels': sanitize_channel_targets(
                cfg.get('extra_channel_targets') or cfg.get('extra_channels') or {}
            ),
            'events': cfg.get('alert_events', []),
            'backlog_threshold': int(cfg.get('queue_backlog_threshold', 10)),
            'gpu_temp_threshold': int(cfg.get('gpu_temp_threshold', 85)),
            'cpu_threshold': int(cfg.get('cpu_percent_threshold', 95)),
            'memory_threshold': int(cfg.get('memory_percent_threshold', 90)),
            'swap_threshold': int(cfg.get('swap_percent_threshold', 80)),
            'disk_threshold': int(cfg.get('disk_used_percent_threshold', 90)),
            'gpu_memory_threshold': int(cfg.get('gpu_memory_percent_threshold', 90)),
            'gpu_power_threshold': int(cfg.get('gpu_power_percent_threshold', 90)),
            'cpu_power_threshold': int(cfg.get('cpu_power_percent_threshold', 90)),
        }

    @staticmethod
    def _pushplus_targets(raw):
        targets = sanitize_pushplus_targets(raw.get('pushplus_targets'))
        if targets:
            return targets
        token = str(raw.get('pushplus_token', '')).strip()
        if not token:
            return []
        return [{
            'id': 'legacy-default',
            'name': '默认 PushPlus',
            'token': token,
            'enabled': bool(raw.get('pushplus_enabled', False)),
        }]

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
            self.log.warning_event('alert_triggered', source='notification')
        if cfg['toast']:
            self._toast(label, text)
        if cfg['sound']:
            self._sound()
        for target in cfg['pushplus_targets']:
            if target['enabled'] and target['token']:
                self._pushplus(target, label, text)
        send_channel_notifications(cfg['channels'], label, text, logger=self.log)

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

    def _check_threshold(self, state_key, event_type, value, threshold, detail):
        """只在阈值状态首次进入时告警，恢复到回滞线以下后允许再次告警。"""
        with self._lock:
            previous = self._threshold_states.get(state_key, False)
            active = value >= (threshold - 5 if previous else threshold)
            self._threshold_states[state_key] = active
        if active and not previous:
            self.notify(event_type, detail)

    def check_metrics(self, metrics):
        """检查采样指标，统一处理阈值、回滞和多设备告警去重。"""
        cfg = self._notify_config()
        self._check_threshold(
            'cpu_overload', 'cpu_overload',
            metrics.get('cpu_percent', 0), cfg['cpu_threshold'],
            f"CPU {metrics.get('cpu_percent', 0)}% 超过阈值 {cfg['cpu_threshold']}%",
        )
        self._check_threshold(
            'memory_pressure', 'memory_pressure',
            metrics.get('mem_percent', 0), cfg['memory_threshold'],
            f"内存 {metrics.get('mem_percent', 0)}% 超过阈值 {cfg['memory_threshold']}%",
        )
        self._check_threshold(
            'swap_pressure', 'swap_pressure',
            metrics.get('swap_percent', 0), cfg['swap_threshold'],
            f"交换区 {metrics.get('swap_percent', 0)}% 超过阈值 {cfg['swap_threshold']}%",
        )
        self._check_threshold(
            'disk_space_low', 'disk_space_low',
            metrics.get('disk_used_percent', 0), cfg['disk_threshold'],
            f"磁盘已使用 {metrics.get('disk_used_percent', 0)}% 超过阈值 {cfg['disk_threshold']}%",
        )

        for gpu in metrics.get('gpus', []):
            index = gpu.get('index', 0)
            temperature = gpu.get('temp')
            if temperature is not None:
                self._check_threshold(
                    f'gpu_overheat:{index}', 'gpu_overheat',
                    temperature, cfg['gpu_temp_threshold'],
                    f"GPU{index} 温度 {temperature}℃ 超过阈值 {cfg['gpu_temp_threshold']}℃",
                )
            memory_percent = gpu.get('mem_used_percent')
            if memory_percent is not None:
                self._check_threshold(
                    f'gpu_memory_pressure:{index}', 'gpu_memory_pressure',
                    memory_percent, cfg['gpu_memory_threshold'],
                    f"GPU{index} 显存 {memory_percent}% 超过阈值 {cfg['gpu_memory_threshold']}%",
                )
            power = gpu.get('power_w')
            power_cap = gpu.get('power_static_cap_w')
            if power is not None and power_cap:
                power_percent = power / power_cap * 100
                self._check_threshold(
                    f'gpu_power_high:{index}', 'gpu_power_high',
                    power_percent, cfg['gpu_power_threshold'],
                    f"GPU{index} 功耗 {power:.1f}W，占静态上限 {power_percent:.1f}%",
                )

        for cpu in metrics.get('cpus', []):
            index = cpu.get('index', 0)
            power = cpu.get('power_w')
            power_cap = cpu.get('power_static_cap_w')
            if power is not None and power_cap:
                power_percent = power / power_cap * 100
                self._check_threshold(
                    f'cpu_power_high:{index}', 'cpu_power_high',
                    power_percent, cfg['cpu_power_threshold'],
                    f"CPU{index} 功耗 {power:.1f}W，占静态上限 {power_percent:.1f}%",
                )

    def notify_test(self):
        """测试推送：走全部启用渠道，不受 alert_events 过滤"""
        cfg = self._notify_config()
        text = '这是一条测试通知'
        if self.log:
            self.log.info_event('test_push', source='notification')
        if cfg['toast']:
            self._toast('测试通知', text)
        if cfg['sound']:
            self._sound()
        for target in cfg['pushplus_targets']:
            if target['enabled'] and target['token']:
                self._pushplus(target, '测试通知', text)
        send_channel_notifications(cfg['channels'], '测试通知', text, logger=self.log)

    def notify_client_task(self, task, event_type):
        """仅按当前任务携带的私有配置发送客户端任务提醒。"""
        raw = task.payload.get('client_notifications') or {}
        if event_type not in raw.get('events', []):
            return
        language = raw.get('lang', task.payload.get('lang', 'zh-CN'))
        language = language if language in CLIENT_TASK_TEXT else 'zh-CN'
        title, content = CLIENT_TASK_TEXT[language][event_type]
        content = content.format(model=_client_task_model_label(task.model, language))
        for target in self._pushplus_targets(raw):
            if target['enabled'] and target['token']:
                self._pushplus(
                    target,
                    title,
                    content,
                    client_id=task.client_id,
                    client_name=raw.get('client_name', ''),
                )
        send_channel_notifications(
            raw.get('channel_targets') or raw.get('channels') or {},
            title,
            content,
            logger=self.log,
            client_id=task.client_id,
            client_name=raw.get('client_name', ''),
        )

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

    def _pushplus(self, target, title, content, client_id=None, client_name=None):
        def worker():
            body = json.dumps({
                'token': target['token'],
                'title': f'斑图系统 · {title}',
                'content': content,
                'template': 'txt',
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
                        self.log.error_event(
                            'pushplus_failed',
                            source='notification',
                            client_id=client_id,
                            client_name=client_name,
                            detail={'name': target['name']},
                        )
        threading.Thread(target=worker, daemon=True).start()
