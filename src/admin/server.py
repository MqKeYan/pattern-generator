"""后台管理中心服务 - FastAPI 应用，仅监听 127.0.0.1

安全：Host 头校验（防 DNS rebinding）、Origin 同源校验、状态变更接口要求
自定义头 X-Requested-With（防跨站请求）、WS 端点内校验 Origin。
"""

import asyncio
import re
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

if getattr(sys, 'frozen', False):
    base_path = os.path.join(sys._MEIPASS, 'src', 'admin')
else:
    base_path = os.path.dirname(__file__)

from admin.logger import LOG_DIR
from admin.reports import generate_report
from admin.websocket import ConnectionManager, check_ws_origin, push_loop, STARTED_AT
from app_context import asset_version, service_info as host_service_info
from settings import public_settings, reset_settings
from version import VERSION
from security import (SessionStore, authenticate_request, authenticate_websocket,
                      RequestBodyLimitMiddleware, set_session_cookie,
                      valid_host_and_origin)


_LOG_FILENAME_RE = re.compile(
    r'^(?:\d{4}-\d{2}-\d{2}\.log|'
    r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\d+(?:_\d+)?\.log)$')


@asynccontextmanager
async def lifespan(_app):
    """启动任务调度与监控（幂等，主服务共用同一单例）+ 推送循环；停止时关闭 WS 连接"""
    ctx = _app.state.ctx
    ctx['task_queue'].start()
    ctx['monitor'].start()
    manager = _app.state.manager
    task = asyncio.create_task(push_loop(manager, ctx))
    yield
    task.cancel()
    await manager.close_all()


class AdminApp:
    """承载路由的 FastAPI 应用工厂（单例创建一次）"""

    def __init__(self, ctx, shutdown_event):
        self.ctx = ctx
        self.shutdown_event = shutdown_event
        # 运行期间保持实际监听端口，配置中的新端口只在重启后接管服务。
        self.bound_port = int(ctx['settings'].get('admin_port', 5001))
        self.manager = ConnectionManager()
        self.sessions = SessionStore()
        self.app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
        self.app.add_middleware(RequestBodyLimitMiddleware, settings=ctx['settings'])
        self.app.state.manager = self.manager
        self.app.state.ctx = ctx
        self._mount_static()
        self._register_middleware()
        self._register_routes()

    def _mount_static(self):
        self.app.mount('/admin/static', StaticFiles(directory=os.path.join(base_path, 'static')), name='admin-static')
        # 共享静态资源：直接挂载主服务目录（i18n.js、style.css、plotly、字体只打一份）
        web_static = os.path.join(os.path.dirname(base_path), 'web', 'static')
        self.app.mount('/static', StaticFiles(directory=web_static), name='shared-static')
        self.templates = Jinja2Templates(directory=os.path.join(base_path, 'templates'))

    def _register_middleware(self):
        app = self.app
        ctx = self.ctx

        @app.middleware('http')
        async def security_middleware(request: Request, call_next):
            settings = ctx['settings']
            host = request.headers.get('host', '')
            allowed_hosts = (f'127.0.0.1:{self.bound_port}', f'localhost:{self.bound_port}')
            if host not in allowed_hosts:
                return JSONResponse({'error': '后台仅允许本机访问'}, status_code=403)

            try:
                content_length = int(request.headers.get('content-length', '0'))
            except ValueError:
                return JSONResponse({'error': '请求体长度无效'}, status_code=400)
            if content_length > int(settings.get('max_request_body_bytes', 2 * 1024 * 1024)):
                return JSONResponse({'error': '请求体过大'}, status_code=413)

            if not valid_host_and_origin(request.headers, set(allowed_hosts)):
                return JSONResponse({'error': '跨站请求被拒绝'}, status_code=403)

            # 状态变更接口要求自定义头（跨站表单无法携带）
            if request.method in ('POST', 'PUT', 'DELETE') and \
                    request.headers.get('x-requested-with') != 'XMLHttpRequest':
                return JSONResponse({'error': '缺少安全头'}, status_code=403)

            if request.url.path.startswith('/admin/api') and \
                    authenticate_request(request, self.sessions, cookie_base='admin_session') is None:
                return JSONResponse({'error': '需要管理员会话'}, status_code=401)

            response = await call_next(request)
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            response.headers['Referrer-Policy'] = 'no-referrer'
            return response

    def _register_routes(self):
        app = self.app
        ctx = self.ctx

        def ok(data=None):
            return {'success': True, **(data or {})}

        def fail(message, status=400):
            return JSONResponse({'error': message}, status_code=status)

        # ---------- 页面 ----------

        @app.get('/')
        async def root():
            from fastapi.responses import RedirectResponse
            return RedirectResponse('/admin/')

        @app.get('/admin/')
        async def admin_page(request: Request):
            settings = ctx['settings']
            # 与主界面共用同一份服务信息（软件运行主机的信息，见 app_context.service_info）
            service_info = host_service_info()

            asset_ver = asset_version(
                os.path.join(base_path, 'static', 'js', 'admin.js'),
                os.path.join(base_path, 'static', 'css', 'admin.css'),
                os.path.join(os.path.dirname(base_path), 'web', 'static', 'js', 'i18n.js'),
                os.path.join(os.path.dirname(base_path), 'web', 'static', 'css', 'style.css'),
            )

            response = self.templates.TemplateResponse(request=request, name='admin.html', context={
                'init_config': {
                    'version': VERSION,
                    'asset_ver': asset_ver,
                    'port': int(settings.get('port', 5000)),
                    'admin_port': int(settings.get('admin_port', 5001)),
                    'log_dir': str(LOG_DIR),
                    'service_info': service_info,
                },
            })
            token = self.sessions.issue(ip=request.client.host if request.client else '')
            set_session_cookie(response, token, secure=request.url.scheme == 'https',
                               cookie_base='admin_session')
            return response

        # ---------- WebSocket ----------

        @app.websocket('/admin/ws')
        async def ws_endpoint(ws: WebSocket):
            host = ws.headers.get('host', '')
            if host not in (f'127.0.0.1:{self.bound_port}', f'localhost:{self.bound_port}') or \
                    not check_ws_origin(ws, host):
                await ws.close(code=4003)
                return
            if authenticate_websocket(ws, self.sessions, cookie_base='admin_session') is None:
                await ws.close(code=4003)
                return
            await self.manager.connect(ws)
            try:
                while True:
                    await ws.receive_text()  # 保活；客户端无需发送业务消息
            except WebSocketDisconnect:
                pass
            except Exception:
                pass
            finally:
                await self.manager.disconnect(ws)

        # ---------- 监控 ----------

        @app.get('/admin/api/metrics')
        async def metrics():
            return ok({
                'started_at': STARTED_AT,
                'current': ctx['monitor'].get_metrics(),
                'history': ctx['monitor'].get_history(),
                'peaks': ctx['monitor'].get_peaks(),
                'counts': ctx['task_queue'].counts(),
                'clients_summary': ctx['clients'].summary(),
            })

        # ---------- 客户端管理 ----------

        @app.get('/admin/api/clients')
        async def clients_list():
            return ok({'clients': ctx['clients'].list(), 'summary': ctx['clients'].summary()})

        def _pause_client(client_id):
            ctx['task_queue'].cancel_client_tasks(client_id, by='admin')
            ctx['clients'].mark_status(client_id, 'paused')

        @app.post('/admin/api/client/{client_id}/pause')
        async def pause_client(client_id: str):
            if not ctx['clients'].get(client_id):
                return fail('客户端不存在', 404)
            _pause_client(client_id)
            ctx['log'].audit(f'暂停客户端 {client_id[:8]}')
            return ok()

        @app.post('/admin/api/client/{client_id}/resume')
        async def resume_client(client_id: str):
            if not ctx['clients'].get(client_id):
                return fail('客户端不存在', 404)
            ctx['clients'].mark_status(client_id, 'online', force=True)
            ctx['log'].audit(f'恢复客户端 {client_id[:8]}')
            return ok()

        @app.post('/admin/api/client/{client_id}/kick')
        async def kick_client(client_id: str):
            client = ctx['clients'].get(client_id)
            if not client:
                return fail('客户端不存在', 404)
            ctx['task_queue'].cancel_client_tasks(client_id, by='admin')
            ctx['client_cache'].remove_client(client_id)
            ctx['access'].add_blacklist(ip=client.ip, client_id=client_id)
            ctx['clients'].mark_status(client_id, 'offline')
            ctx['log'].audit(f'踢出客户端 {client_id[:8]}（IP {client.ip} 已同时封禁）')
            ctx['notifier'].notify('client_kicked', f'{client.client_name or client_id[:8]} ({client.ip})')
            return ok()

        @app.post('/admin/api/client/{client_id}/clear-cache')
        async def clear_client_cache(client_id: str):
            removed = ctx['client_cache'].remove_client(client_id)
            ctx['log'].audit(f'清理客户端缓存 {client_id[:8]}')
            return ok({'removed': removed})

        @app.post('/admin/api/client/{client_id}/delete')
        async def delete_client(client_id: str):
            if not ctx['clients'].get(client_id):
                return fail('客户端不存在', 404)
            ctx['task_queue'].cancel_client_tasks(client_id, by='admin')
            closed = ctx['presence_sockets'].close_all(client_id)
            ctx['clients'].delete(client_id)
            ctx['log'].audit(f'删除客户端记录 {client_id[:12]}（已断开 {closed} 个页面连接并取消其任务）')
            return ok()

        @app.post('/admin/api/client/{client_id}/remark')
        async def set_remark(client_id: str, request: Request):
            data = await request.json()
            if not ctx['clients'].set_remark(client_id, remark=data.get('remark'), tags=data.get('tags')):
                return fail('客户端不存在', 404)
            ctx['log'].audit(f'更新客户端备注 {client_id[:8]}')
            return ok()

        @app.post('/admin/api/clear-all-cache')
        async def clear_all_cache():
            ctx['client_cache'].clear()
            ctx['log'].audit('清空所有客户端缓存')
            return ok()

        @app.post('/admin/api/stats/clear')
        async def clear_stats():
            ctx['clients'].clear_all_stats()
            ctx['log'].audit('清除全部客户端统计')
            return ok()

        @app.post('/admin/api/counters/reset')
        async def reset_counters():
            ctx['clients'].reset_counters()
            ctx['log'].audit('重置全部客户端累计计数')
            return ok()

        # ---------- 任务队列 ----------

        @app.get('/admin/api/tasks')
        async def tasks_all():
            q = ctx['task_queue']
            return ok({
                'running': q.list_running(),
                'waiting': q.list_waiting(),
                'history': q.list_history()[-100:],
                'counts': q.counts(),
            })

        @app.get('/admin/api/dead-tasks')
        async def dead_tasks():
            return ok({'tasks': ctx['task_queue'].list_dead()})

        @app.get('/admin/api/task/{task_id}')
        async def task_detail(task_id: str):
            snap = ctx['task_queue'].get(task_id)
            if snap is None:
                return fail('任务不存在', 404)
            return ok({'task': snap})

        @app.post('/admin/api/task/{task_id}/cancel')
        async def admin_cancel_task(task_id: str):
            queue_task = ctx['task_queue'].get_task(task_id)
            if queue_task is None:
                return fail('任务不存在', 404)
            task_queue = ctx['task_queue']
            okr, why = task_queue.cancel(task_id, by='admin')
            ctx['log'].audit(f'取消任务 {task_id[:8]} ({why})')
            return ok({'state': why}) if okr else fail(f'无法取消（{why}）')

        @app.post('/admin/api/task/{task_id}/retry')
        async def admin_retry_task(task_id: str):
            if not ctx['task_queue'].retry(task_id):
                return fail('仅失败（死信）任务可重试')
            ctx['log'].audit(f'重试死信任务 {task_id[:8]}')
            return ok()

        @app.delete('/admin/api/task/{task_id}')
        async def admin_delete_task(task_id: str):
            if not ctx['task_queue'].remove_dead(task_id):
                return fail('任务不存在或不在死信队列', 404)
            ctx['log'].audit(f'删除死信任务 {task_id[:8]}')
            return ok()

        @app.post('/admin/api/tasks/cancel-all')
        async def cancel_all_tasks():
            ctx['task_queue'].cancel_all(by='admin')
            ctx['log'].audit('中断所有任务')
            return ok()

        @app.post('/admin/api/tasks/clear-queue')
        async def clear_queue():
            n = ctx['task_queue'].clear_queue()
            ctx['log'].audit(f'清空等待队列（{n} 个）')
            return ok({'cleared': n})

        # ---------- 访问控制 ----------

        @app.get('/admin/api/access-control')
        async def get_access():
            return ok({'lists': ctx['access'].get_lists()})

        @app.post('/admin/api/access-control')
        async def update_access(request: Request):
            data = await request.json()
            action = data.get('action')
            kind = data.get('kind')
            entry = str(data.get('entry', '') or '')
            target = data.get('list')
            if action not in ('add', 'remove') or kind not in ('ips', 'client_ids') or not entry:
                return fail('参数无效')
            try:
                if target == 'blacklist':
                    ctx['access'].update_blacklist(action, kind, entry)
                elif target == 'whitelist':
                    ctx['access'].update_whitelist(action, kind, entry)
                else:
                    return fail('名单类型无效')
            except ValueError as e:
                return fail(f'IP 格式无效: {e}')
            ctx['log'].audit(f'访问控制: {target} {action} {kind} {entry}')
            return ok({'lists': ctx['access'].get_lists()})

        @app.get('/admin/api/access-events')
        async def access_events():
            return ok({'events': ctx['access'].denied_events()})

        @app.get('/admin/api/alerts')
        async def alerts():
            return ok({'alerts': list(ctx['notifier'].alerts)})

        # ---------- 报表 ----------

        @app.get('/admin/api/reports')
        async def reports(type: str = 'tasks', format: str = 'csv'):
            try:
                filename, blob = generate_report(
                    type, format,
                    clients_list=ctx['clients'].list(),
                    tasks_list=ctx['task_queue'].list_history() + ctx['task_queue'].list_dead(),
                    peaks=ctx['monitor'].get_peaks(),
                    denied=ctx['access'].denied_events(),
                    alerts=list(ctx['notifier'].alerts),
                )
            except (ValueError, RuntimeError) as e:
                return fail(str(e))
            media = {'csv': 'text/csv', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     'json': 'application/json'}[format]
            ctx['log'].audit(f'导出报表 {filename}')
            return Response(blob, media_type=media, headers={
                'Content-Disposition': f'attachment; filename="{filename}"'})

        # ---------- 日志 ----------

        @app.get('/admin/api/logs')
        async def logs(since: int = 0):
            log = ctx['log']
            return ok({'entries': log.replay(since_seq=since), 'file': log.current_file()})

        @app.get('/admin/api/logs/files')
        async def logs_files():
            """列出当前运行和历史运行日志，旧日期日志保持可下载。"""
            files = []
            try:
                for path in LOG_DIR.iterdir():
                    if not path.is_file() or not _LOG_FILENAME_RE.fullmatch(path.name):
                        continue
                    stat = path.stat()
                    files.append({
                        'name': path.name,
                        'size': stat.st_size,
                        'modified_at': stat.st_mtime,
                    })
            except OSError as exc:
                return fail(f'读取日志目录失败: {type(exc).__name__}', 500)
            files.sort(key=lambda item: item['modified_at'], reverse=True)
            current = ctx['log'].current_file()
            return ok({'files': files, 'current': Path(current).name if current else None})

        @app.get('/admin/api/logs/download')
        async def logs_download(filename: str = '', date: str = ''):
            """按安全文件名下载单次运行日志。"""
            # 兼容旧版按日期下载请求，旧文件仍可继续读取。
            if not filename and re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
                filename = f'{date}.log'
            if not _LOG_FILENAME_RE.fullmatch(filename) or Path(filename).name != filename:
                return fail('日志文件名无效')
            path = LOG_DIR / filename
            if not path.is_file():
                return fail('日志文件不存在', 404)
            return Response(path.read_bytes(), media_type='text/plain',
                            headers={'Content-Disposition': f'attachment; filename="{filename}"'})

        # ---------- 通知 ----------

        @app.post('/admin/api/notifications/test')
        async def notifications_test():
            ctx['notifier'].notify_test()
            return ok()

        # ---------- 系统设置 ----------

        @app.get('/admin/api/settings')
        async def get_settings():
            return ok({'settings': public_settings(ctx['settings'])})

        @app.post('/admin/api/settings')
        async def save_settings(request: Request):
            try:
                data = await request.json()
            except Exception:
                return fail('请求体必须是 JSON')
            try:
                from settings import update_settings as us
                us(**data)
            except (ValueError, TypeError) as e:
                return fail(str(e))
            ctx['reload_runtime_settings']()
            ctx['log'].audit('修改系统设置')
            return ok({'settings': public_settings(ctx['settings']), 'restart_required': True})

        @app.post('/admin/api/settings/reset')
        async def settings_reset():
            reset_settings()
            ctx['reload_runtime_settings']()
            ctx['log'].audit('恢复默认设置')
            return ok({'settings': public_settings(ctx['settings']), 'restart_required': True})

        # ---------- 服务控制 ----------

        @app.post('/admin/api/shutdown')
        async def shutdown():
            ctx['log'].audit('请求停止所有服务')
            self.shutdown_event.set()
            return ok()


def create_admin_app(ctx, shutdown_event):
    """创建后台应用单例"""
    return AdminApp(ctx, shutdown_event).app
