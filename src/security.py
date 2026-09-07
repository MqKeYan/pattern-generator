"""主服务安全辅助函数：可信来源、浏览器会话和脚本访问密钥。"""

import hashlib
import hmac
import os
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi.responses import JSONResponse


SESSION_TTL_SECONDS = 24 * 60 * 60
SESSION_LIMIT = 4096


class RequestBodyTooLarge(Exception):
    """实际接收的 HTTP 请求体超过允许上限。"""


class RequestBodyLimitMiddleware:
    """按实际接收字节限制请求体，兼容未声明 Content-Length 的分块请求。"""

    def __init__(self, app, settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                limit = int(self.settings.get('max_request_body_bytes', 2 * 1024 * 1024))
                if received > limit:
                    raise RequestBodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            response = JSONResponse({'error': '请求体过大'}, status_code=413)
            await response(scope, receive, send)


@dataclass
class AuthContext:
    """当前请求的认证主体。"""

    subject: str
    client_id: str = ''
    is_access_key: bool = False


class SessionStore:
    """进程内浏览器会话存储；服务重启后旧 Cookie 自动失效。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._sessions = {}

    def issue(self, client_id='', ip=''):
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._purge_locked(now)
            self._sessions[token] = {
                'client_id': str(client_id or ''),
                'ip': str(ip or ''),
                'last_seen': now,
            }
            while len(self._sessions) > SESSION_LIMIT:
                self._sessions.pop(next(iter(self._sessions)))
        return token

    def authenticate(self, token, client_id='', ip=''):
        if not token:
            return None
        now = time.time()
        with self._lock:
            self._purge_locked(now)
            session = self._sessions.get(token)
            if session is None:
                return None
            bound_client = session['client_id']
            if bound_client and client_id and bound_client != client_id:
                return None
            if client_id and not bound_client:
                session['client_id'] = client_id
                bound_client = client_id
            session['last_seen'] = now
            return AuthContext(subject=f'session:{token}', client_id=bound_client,
                               is_access_key=False)

    def _purge_locked(self, now):
        expired = [token for token, item in self._sessions.items()
                   if now - item['last_seen'] > SESSION_TTL_SECONDS]
        for token in expired:
            self._sessions.pop(token, None)


def access_key_configured():
    """脚本访问密钥只从环境变量读取，绝不进入页面配置。"""
    return os.environ.get('PATTERN_ACCESS_KEY', '').strip()


def _cookie_token(cookies, cookie_base):
    return cookies.get(f'__Host-{cookie_base}') or cookies.get(cookie_base)


def authenticate_request(request, sessions, client_id='', cookie_base='pattern_session'):
    """按访问密钥或 HttpOnly Cookie 认证请求。"""
    configured_key = access_key_configured()
    supplied_key = request.headers.get('x-pattern-access-key', '')
    if configured_key and hmac.compare_digest(supplied_key, configured_key):
        digest = hashlib.sha256(configured_key.encode('utf-8')).hexdigest()[:16]
        return AuthContext(subject=f'key:{digest}', client_id=str(client_id or ''),
                           is_access_key=True)

    token = _cookie_token(request.cookies, cookie_base)
    ip = request.client.host if request.client else ''
    return sessions.authenticate(token, str(client_id or ''), ip)


def authenticate_websocket(ws, sessions, client_id='', cookie_base='pattern_session'):
    """认证 WebSocket 握手；Cookie 由浏览器自动携带。"""
    configured_key = access_key_configured()
    supplied_key = ws.headers.get('x-pattern-access-key', '')
    if configured_key and hmac.compare_digest(supplied_key, configured_key):
        digest = hashlib.sha256(configured_key.encode('utf-8')).hexdigest()[:16]
        return AuthContext(subject=f'key:{digest}', client_id=str(client_id or ''),
                           is_access_key=True)
    token = _cookie_token(ws.cookies, cookie_base)
    ip = ws.client.host if ws.client else ''
    return sessions.authenticate(token, str(client_id or ''), ip)


def trusted_hosts(settings, port):
    """返回带端口的可信 Host 集合；局域网地址必须显式配置。"""
    hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
    for item in settings.get('allowed_hosts', []):
        value = str(item).strip().lower()
        if not value:
            continue
        hosts.add(value if ':' in value else f'{value}:{port}')
    return hosts


def valid_host_and_origin(headers, allowed_hosts):
    """严格校验 Host 与 Origin，拒绝伪造来源。"""
    host = headers.get('host', '').strip().lower()
    if not host or host not in allowed_hosts:
        return False
    origin = headers.get('origin')
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    return parsed.scheme in ('http', 'https') and parsed.netloc.lower() == host


def set_session_cookie(response, token, secure=False, cookie_base='pattern_session'):
    """设置仅脚本不可读、严格同站的浏览器会话 Cookie。"""
    name = f'__Host-{cookie_base}' if secure else cookie_base
    response.set_cookie(name, token, httponly=True, samesite='strict',
                        secure=secure, path='/', max_age=SESSION_TTL_SECONDS)
