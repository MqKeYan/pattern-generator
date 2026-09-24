"""可选通知渠道适配器。

现有 Windows 通知、浏览器通知、提示音和 PushPlus 不经过本模块；
本模块只负责新增渠道，并在单独线程中发送，避免阻塞任务或告警主流程。
"""

import base64
import copy
import hashlib
import hmac
import json
import re
import smtplib
import ssl
import threading
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage


CHANNEL_DEFAULTS = {
    'webhook': {'enabled': False, 'url': ''},
    'email': {
        'enabled': False, 'host': '', 'port': 465, 'ssl': True, 'starttls': False,
        'username': '', 'password': '', 'sender': '', 'recipient': '',
    },
    'telegram': {'enabled': False, 'token': '', 'chat_id': ''},
    'discord': {'enabled': False, 'url': ''},
    'dingtalk': {'enabled': False, 'url': '', 'secret': ''},
    'feishu': {'enabled': False, 'url': '', 'secret': ''},
    'wecom': {'enabled': False, 'url': ''},
}

CHANNEL_SECRET_FIELDS = {
    'webhook': ('url',),
    'email': ('password',),
    'telegram': ('token',),
    'discord': ('url',),
    'dingtalk': ('url', 'secret'),
    'feishu': ('url', 'secret'),
    'wecom': ('url',),
}

CHANNEL_LABELS = {
    'webhook': '通用Webhook',
    'email': 'SMTP邮件',
    'telegram': 'Telegram',
    'discord': 'Discord',
    'dingtalk': '钉钉',
    'feishu': '飞书',
    'wecom': '企业微信',
}

CHANNEL_TARGET_LIMIT = 20
_CHANNEL_TARGET_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
PUSHPLUS_TARGET_LIMIT = 20
_PUSHPLUS_TARGET_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def sanitize_pushplus_targets(data):
    """规范化多个 PushPlus 推送目标，凭据仅保留在服务端或客户端本地。"""
    if not isinstance(data, list):
        return []
    targets = []
    seen_ids = set()
    for index, raw in enumerate(data):
        if len(targets) >= PUSHPLUS_TARGET_LIMIT:
            break
        if not isinstance(raw, dict):
            continue
        target_id = str(raw.get('id', '')).strip()
        if not _PUSHPLUS_TARGET_ID_RE.fullmatch(target_id) or target_id in seen_ids:
            continue
        name = str(raw.get('name', '')).strip()[:40] or f'PushPlus {index + 1}'
        token = str(raw.get('token', '')).strip()[:256]
        targets.append({
            'id': target_id,
            'name': name,
            'token': token,
            'enabled': bool(raw.get('enabled')),
        })
        seen_ids.add(target_id)
    return targets


def public_pushplus_targets(data):
    """返回可安全交给浏览器的目标列表，不泄露 Token。"""
    return [
        {
            'id': target['id'],
            'name': target['name'],
            'enabled': target['enabled'],
            'token_configured': bool(target['token']),
        }
        for target in sanitize_pushplus_targets(data)
    ]


def sanitize_channel_settings(data):
    """仅保留已支持渠道及其字段，避免配置结构失控。"""
    result = copy.deepcopy(CHANNEL_DEFAULTS)
    if not isinstance(data, dict):
        return result
    for name, values in data.items():
        if name not in result or not isinstance(values, dict):
            continue
        for key, value in values.items():
            if key not in result[name]:
                continue
            if key == 'enabled' or key in ('ssl', 'starttls'):
                if isinstance(value, bool):
                    result[name][key] = value
            elif key == 'port':
                if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535:
                    result[name][key] = value
            elif isinstance(value, str) and len(value) <= 1024:
                result[name][key] = value.strip()
    return result


def public_channel_settings(data):
    """隐藏令牌、密码和 Webhook 地址，只返回是否已配置。"""
    result = sanitize_channel_settings(data)
    for name, fields in CHANNEL_SECRET_FIELDS.items():
        channel = result[name]
        for field in fields:
            channel[f'{field}_configured'] = bool(channel.get(field))
            channel.pop(field, None)
    return result


def sanitize_channel_targets(data):
    """规范化按平台分组的多个第三方推送目标。"""
    if not isinstance(data, dict):
        return {}
    result = {}
    for name, raw_items in data.items():
        if name not in CHANNEL_DEFAULTS:
            continue
        # 兼容旧版每个平台只有一个配置对象的结构。
        items = raw_items if isinstance(raw_items, list) else ([raw_items] if isinstance(raw_items, dict) else [])
        targets = []
        seen_ids = set()
        for index, raw in enumerate(items):
            if len(targets) >= CHANNEL_TARGET_LIMIT or not isinstance(raw, dict):
                continue
            target_id = str(raw.get('id', '')).strip()
            if not target_id:
                target_id = f'legacy-{name}' if index == 0 else f'{name}-{index + 1}'
            if not _CHANNEL_TARGET_ID_RE.fullmatch(target_id) or target_id in seen_ids:
                continue
            values = sanitize_channel_settings({name: raw})[name]
            values['enabled'] = bool(raw.get('enabled'))
            values.update({
                'id': target_id,
                'name': str(raw.get('name', '')).strip()[:40] or f'默认{CHANNEL_LABELS[name]}',
            })
            targets.append(values)
            seen_ids.add(target_id)
        result[name] = targets
    return result


def public_channel_targets(data):
    """返回多个第三方目标的公开信息，敏感字段只返回配置状态。"""
    public = {}
    targets = sanitize_channel_targets(data)
    for name in CHANNEL_DEFAULTS:
        public[name] = []
        for target in targets.get(name, []):
            safe = public_channel_settings({name: target})[name]
            public[name].append({
                'id': target['id'],
                'name': target['name'],
                **safe,
            })
    return public


def merge_channel_targets(existing, incoming):
    """按目标 ID 合并配置，后台留空敏感字段时保留原凭据。"""
    previous = sanitize_channel_targets(existing)
    incoming = incoming if isinstance(incoming, dict) else {}
    merged = {name: [dict(target) for target in previous.get(name, [])] for name in CHANNEL_DEFAULTS}
    for name in CHANNEL_DEFAULTS:
        if name not in incoming:
            continue
        old_by_id = {target['id']: target for target in previous.get(name, [])}
        items = incoming.get(name) if isinstance(incoming.get(name), list) else []
        result = []
        for raw in items[:CHANNEL_TARGET_LIMIT]:
            if not isinstance(raw, dict):
                continue
            candidate = dict(raw)
            old = old_by_id.get(str(candidate.get('id', '')).strip(), {})
            for field in CHANNEL_SECRET_FIELDS.get(name, ()):
                if not str(candidate.get(field, '')).strip() and old.get(field):
                    candidate[field] = old[field]
            result.append(candidate)
        merged[name] = result
    return sanitize_channel_targets(merged)


def _post_json(url, payload, timeout=5):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json; charset=utf-8'},
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read(1)


def _signed_robot_url(url, secret):
    if not secret:
        return url, None
    timestamp = str(int(time.time() * 1000))
    message = f'{timestamp}\n{secret}'.encode('utf-8')
    sign = base64.b64encode(hmac.new(secret.encode('utf-8'), message, hashlib.sha256).digest()).decode()
    query = urllib.parse.urlencode({'timestamp': timestamp, 'sign': sign})
    separator = '&' if '?' in url else '?'
    return f'{url}{separator}{query}', {'timestamp': timestamp, 'sign': sign}


def _send_email(channel, title, content, timeout):
    message = EmailMessage()
    message['From'] = channel['sender'] or channel['username']
    message['To'] = channel['recipient']
    message['Subject'] = f'斑图系统 · {title}'
    message.set_content(content)
    if channel['ssl']:
        with smtplib.SMTP_SSL(channel['host'], channel['port'], timeout=timeout) as client:
            if channel['username']:
                client.login(channel['username'], channel['password'])
            client.send_message(message)
        return
    with smtplib.SMTP(channel['host'], channel['port'], timeout=timeout) as client:
        if channel['starttls']:
            client.starttls(context=ssl.create_default_context())
        if channel['username']:
            client.login(channel['username'], channel['password'])
        client.send_message(message)


def _send_channel(name, channel, title, content, timeout):
    text = f'{title}\n{content}'
    if name == 'webhook':
        _post_json(channel['url'], {'title': title, 'content': content, 'source': '斑图系统'})
    elif name == 'email':
        _send_email(channel, title, content, timeout)
    elif name == 'telegram':
        _post_json(
            f"https://api.telegram.org/bot{channel['token']}/sendMessage",
            {'chat_id': channel['chat_id'], 'text': text[:4096]},
        )
    elif name == 'discord':
        _post_json(channel['url'], {'content': text[:1900]})
    elif name == 'dingtalk':
        url, signature = _signed_robot_url(channel['url'], channel['secret'])
        payload = {'msgtype': 'text', 'text': {'content': text[:2000]}}
        if signature:
            payload['timestamp'] = signature['timestamp']
            payload['sign'] = signature['sign']
        _post_json(url, payload)
    elif name == 'feishu':
        url, signature = _signed_robot_url(channel['url'], channel['secret'])
        payload = {'msg_type': 'text', 'content': {'text': text[:4000]}}
        if signature:
            payload['timestamp'] = signature['timestamp']
            payload['sign'] = signature['sign']
        _post_json(url, payload)
    elif name == 'wecom':
        _post_json(channel['url'], {'msgtype': 'text', 'text': {'content': text[:2000]}})


def _channel_ready(name, channel):
    required = {
        'webhook': ('url',),
        'email': ('host', 'recipient'),
        'telegram': ('token', 'chat_id'),
        'discord': ('url',),
        'dingtalk': ('url',),
        'feishu': ('url',),
        'wecom': ('url',),
    }[name]
    return bool(channel.get('enabled')) and all(str(channel.get(key, '')).strip() for key in required)


def send_channel_notifications(channels, title, content, logger=None, timeout=5,
                               client_id=None, client_name=None):
    """并行发送所有已启用目标，兼容旧版单目标渠道结构。"""
    targets = sanitize_channel_targets(channels)
    for name, channel_list in targets.items():
        for channel in channel_list:
            if not _channel_ready(name, channel):
                continue

            def worker(channel_name=name, channel_config=channel):
                try:
                    _send_channel(channel_name, channel_config, title, content, timeout)
                except Exception:
                    if logger:
                        logger.error_event(
                            'notification_channel_failed',
                            source='notification',
                            client_id=client_id,
                            client_name=client_name,
                            detail={
                                'channel': CHANNEL_LABELS[channel_name],
                                'target_name': channel_config.get('name', ''),
                            },
                        )

            threading.Thread(target=worker, name=f'notify-{name}', daemon=True).start()
