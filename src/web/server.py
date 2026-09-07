"""主界面服务 - FastAPI 应用，提供异步任务提交 API

路由路径与请求/响应 JSON 结构尽量保持 v1.x 兼容；
/api/simulate、/api/animate 由同步返回改为异步提交（返回 task_id）。
"""

import asyncio
import math
import os
import re
import sys
from contextlib import asynccontextmanager
import mimetypes

# 注册字体MIME类型，确保浏览器正确加载本地字体
mimetypes.add_type('font/collection', '.ttc')
mimetypes.add_type('font/otf', '.otf')

# 环境变量设置
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import torch
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

if getattr(sys, 'frozen', False):
    base_path = os.path.join(sys._MEIPASS, 'src', 'web')
else:
    base_path = os.path.dirname(__file__)

from app_context import (access, clients, client_cache, init_config, log,
                         monitor, presence_sockets, settings, task_queue)
from admin.tasks import QueueLimitError
from security import (SessionStore, authenticate_request, authenticate_websocket,
                      RequestBodyLimitMiddleware, set_session_cookie, trusted_hosts,
                      valid_host_and_origin)


@asynccontextmanager
async def lifespan(_app):
    """服务启动时开启任务调度与监控（幂等，后台服务共用同一单例）"""
    task_queue.start()
    monitor.start()
    yield
    task_queue.stop()
    monitor.stop()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(RequestBodyLimitMiddleware, settings=settings)
app.mount('/static', StaticFiles(directory=os.path.join(base_path, 'static')), name='static')
templates = Jinja2Templates(directory=os.path.join(base_path, 'templates'))

from core.config import MODEL_CONFIGS, MODEL_INIT_RANGES, GRID_SIZE  # noqa: E402

MAX_ITERATIONS = 100000
MAX_FRAMES = 2000
# 服务运行期间始终按实际监听端口校验 Host；后台修改端口仅在重启后生效。
BOUND_PORT = int(settings.get('port', 5000))
sessions = SessionStore()

_CLIENT_NAME_RE = re.compile(
    r'''[\w \u3000.,!?;:'"()\[\]{}\-_/\\@#%&+=·，。！？；：、“”‘’（）【】《》、…]+'''
)


def _error(message, status=400):
    return JSONResponse({'error': message}, status_code=status)


@app.middleware('http')
async def security_headers_and_limits(request: Request, call_next):
    """统一限制请求体并添加基础安全响应头。"""
    allowed = trusted_hosts(settings, BOUND_PORT)
    if not valid_host_and_origin(request.headers, allowed):
        return _error('请求来源不受信任', 403)
    try:
        content_length = int(request.headers.get('content-length', '0'))
    except ValueError:
        return _error('请求体长度无效', 400)
    if content_length > int(settings.get('max_request_body_bytes', 2 * 1024 * 1024)):
        return _error('请求体过大', 413)
    if request.method in ('POST', 'PUT', 'DELETE') and \
            request.headers.get('x-requested-with') != 'XMLHttpRequest':
        return _error('缺少安全头', 403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def _client_ip(request):
    """仅信任直连地址，不解析转发头"""
    return request.client.host if request.client else ''


def _client_id(data):
    value = data.get('client_id', '')
    if not isinstance(value, str):
        raise ValueError('client_id 必须是字母、数字、下划线或连字符')
    value = value.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise ValueError('client_id 只能包含字母、数字、下划线和连字符，长度为 1-128')
    return value


def _client_name(data):
    """校验客户端名称：支持多语言文字和常见标点，不支持表情及控制字符。"""
    value = data.get('client_name', '')
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('客户端名称必须是文本')
    value = value.strip()
    if len(value) > 40:
        raise ValueError('客户端名称不能超过40个字符')
    if value and not _CLIENT_NAME_RE.fullmatch(value):
        raise ValueError('客户端名称包含不支持的字符')
    return value


def _strict_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f'{name} 必须是整数')
    return value


def _finite_float(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} 必须是数值')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'{name} 必须是有限数值')
    return number


def _language_code(value):
    """校验界面语言标识，避免非法 JSON 值进入后台任务线程。"""
    if not isinstance(value, str) or not value or len(value) > 32:
        raise ValueError('lang 必须是 1-32 个字符的字符串')
    return value


def _authenticate(request, client_id=''):
    return authenticate_request(request, sessions, client_id)


def _authorize_task(request, task):
    auth = _authenticate(request)
    if auth is None or auth.subject != task.owner:
        return None
    return auth


async def _guard(request):
    """Host/Origin 已由中间件统一校验；此处保留接口以维持路由结构。"""
    return None


def _register_client(data, ip):
    client_id = str(data.get('client_id', '') or '')
    if client_id:
        clients.register_or_touch(
            client_id,
            str(data.get('client_name', '') or ''),
            ip,
            str(data.get('client_session_id', '') or '') or None,
        )
        clients.record_request(client_id)
    return client_id


@app.get('/')
async def index(request: Request):
    """主页面，同时签发 HttpOnly 浏览器会话。"""
    response = templates.TemplateResponse(
        request=request, name='index.html',
        context={'init_config': init_config()})
    token = sessions.issue(ip=_client_ip(request))
    set_session_cookie(response, token, secure=request.url.scheme == 'https')
    return response


def _check_presence_origin(ws):
    """校验前台 WebSocket 的 Host 和 Origin。"""
    return valid_host_and_origin(
        ws.headers, trusted_hosts(settings, BOUND_PORT))


@app.websocket('/api/presence')
async def presence(ws: WebSocket):
    """前台客户端在线连接；连接关闭后立即移除页面会话"""
    if not _check_presence_origin(ws):
        await ws.close(code=4003)
        return
    max_connections = int(settings.get('max_presence_sockets', 2048))
    if not presence_sockets.reserve(max_connections):
        await ws.close(code=4004)
        return
    reserved = True
    await ws.accept()

    client_id = None
    session_id = None
    try:
        data = await asyncio.wait_for(ws.receive_json(), timeout=10)
        try:
            client_id = _client_id(data)
            client_name = _client_name(data)
        except (TypeError, ValueError):
            await ws.close(code=4000)
            return
        session_id = str(data.get('client_session_id', '') or '') or None
        if not client_id or not session_id:
            await ws.close(code=4000)
            return

        if authenticate_websocket(ws, sessions, client_id) is None:
            await ws.close(code=4003)
            return
        ip = ws.client.host if ws.client else ''
        allowed, _reason = access.is_allowed(ip, client_id)
        if not allowed:
            await ws.close(code=4003)
            return
        client = clients.register_or_touch(
            client_id,
            client_name,
            ip,
            session_id,
            websocket=True,
        )
        if client is None:
            await ws.close(code=4004)
            return
        if not presence_sockets.register(
                client_id, session_id, ws,
                int(settings.get('max_presence_sockets_per_client', 4))):
            await ws.close(code=4004)
            return
        presence_sockets.release_reservation()
        reserved = False

        while True:
            await ws.receive()
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        pass
    finally:
        if reserved:
            presence_sockets.release_reservation()
        if client_id and session_id:
            clients.disconnect(client_id, session_id)
            presence_sockets.unregister(client_id, session_id)


@app.post('/api/simulate')
async def run_simulation(request: Request):
    """提交模拟任务（异步）"""
    guard = await _guard(request)
    if guard:
        return guard
    try:
        data = await request.json()
    except Exception:
        return _error('请求体必须是 JSON')
    if not isinstance(data, dict):
        return _error('请求体必须是 JSON 对象')

    try:
        client_id = _client_id(data)
        _client_name(data)
    except ValueError as e:
        return _error(str(e))
    auth = _authenticate(request, client_id)
    if auth is None:
        return _error('缺少有效会话或访问密钥', 401)
    ip = _client_ip(request)

    allowed, reason = access.is_allowed(ip, client_id)
    if not allowed:
        access.record_denied(ip, client_id, reason)
        return _error('访问被拒绝', 403)

    model_name = data.get('model', '模型1')
    if not isinstance(model_name, str) or model_name not in MODEL_CONFIGS:
        return _error(f'模型 "{model_name}" 不存在')

    try:
        iterations = _strict_int(data.get('iterations', 9000), 'iterations')
        raw_params = data.get('params', MODEL_CONFIGS[model_name]['defaults'])
        if not isinstance(raw_params, list):
            raise ValueError('params 必须是数组')
        params = [_finite_float(v, f'params[{i}]') for i, v in enumerate(raw_params)]
        init_x_range = (
            _finite_float(data.get('x_min', MODEL_INIT_RANGES[model_name]['x_range'][0]), 'x_min'),
            _finite_float(data.get('x_max', MODEL_INIT_RANGES[model_name]['x_range'][1]), 'x_max'))
        init_y_range = (
            _finite_float(data.get('y_min', MODEL_INIT_RANGES[model_name]['y_range'][0]), 'y_min'),
            _finite_float(data.get('y_max', MODEL_INIT_RANGES[model_name]['y_range'][1]), 'y_max'))
        lang = _language_code(data.get('lang', 'zh-CN'))
    except (TypeError, ValueError):
        return _error('参数格式无效')

    if not 1 <= iterations <= MAX_ITERATIONS:
        return _error(f'迭代次数须在 1-{MAX_ITERATIONS} 之间')
    if len(params) != len(MODEL_CONFIGS[model_name]['params']):
        return _error('参数数量不匹配')
    if init_x_range[0] > init_x_range[1] or init_y_range[0] > init_y_range[1]:
        return _error('初始范围下限不能大于上限')

    track_points = data.get('track_points') or []
    if not isinstance(track_points, list) or len(track_points) > 8:
        return _error('跟踪点格式无效（最多 8 个）')
    validated_points = []
    for point in track_points:
        if not isinstance(point, dict) or 'x' not in point or 'y' not in point:
            return _error('跟踪点必须包含 x、y 坐标')
        try:
            px = _strict_int(point['x'], '跟踪点 x')
            py = _strict_int(point['y'], '跟踪点 y')
        except (TypeError, ValueError):
            return _error('跟踪点坐标必须是整数')
        if not (0 <= px < GRID_SIZE and 0 <= py < GRID_SIZE):
            return _error(f'跟踪点坐标须在 0-{GRID_SIZE - 1} 之间')
        validated_points.append({'x': px, 'y': py})
    track_points = validated_points

    limit = int(settings.get('request_rate_limit', 10))
    window = int(settings.get('request_rate_window_seconds', 60))
    if not access.check_rate_limit(ip, client_id, limit, window):
        access.record_denied(ip, client_id, 'rate_limit')
        return _error('请求过于频繁，请稍后再试', 429)

    _register_client(data, ip)
    client = clients.get(client_id)
    if client is None:
        return _error('在线客户端数量已达到上限', 429)
    payload = {
        'type': 'simulate', 'model': model_name, 'params': params,
        'iterations': iterations, 'init_x_range': init_x_range, 'init_y_range': init_y_range,
        'track_points': track_points, 'lang': lang,
    }
    try:
        task = task_queue.submit(payload, client_id, owner=auth.subject)
    except QueueLimitError as e:
        return _error(str(e), 429)
    log.info(f"→ 模拟任务提交：{model_name}，迭代{iterations}次（队列位置 {task_queue.queue_position(task.task_id)}）")
    return {
        'task_id': task.task_id, 'status': task.status,
        'queue_position': task_queue.queue_position(task.task_id),
        'paused': client is not None and client.status == 'paused',
    }


@app.post('/api/animate')
async def run_animation(request: Request):
    """提交动画任务（异步）"""
    guard = await _guard(request)
    if guard:
        return guard
    try:
        data = await request.json()
    except Exception:
        return _error('请求体必须是 JSON')
    if not isinstance(data, dict):
        return _error('请求体必须是 JSON 对象')

    try:
        client_id = _client_id(data)
        _client_name(data)
    except ValueError as e:
        return _error(str(e))
    auth = _authenticate(request, client_id)
    if auth is None:
        return _error('缺少有效会话或访问密钥', 401)
    ip = _client_ip(request)

    allowed, reason = access.is_allowed(ip, client_id)
    if not allowed:
        access.record_denied(ip, client_id, reason)
        return _error('访问被拒绝', 403)

    model_name = data.get('model', '模型1')
    if not isinstance(model_name, str) or model_name not in MODEL_CONFIGS:
        return _error(f'模型 "{model_name}" 不存在')

    try:
        frames = _strict_int(data.get('frames', 300), 'frames')
        start_frame = _strict_int(data.get('start_frame', 0), 'start_frame')
        raw_params = data.get('params', MODEL_CONFIGS[model_name]['defaults'])
        if not isinstance(raw_params, list):
            raise ValueError('params 必须是数组')
        params = [_finite_float(v, f'params[{i}]') for i, v in enumerate(raw_params)]
        init_x_range = (
            _finite_float(data.get('x_min', MODEL_INIT_RANGES[model_name]['x_range'][0]), 'x_min'),
            _finite_float(data.get('x_max', MODEL_INIT_RANGES[model_name]['x_range'][1]), 'x_max'))
        init_y_range = (
            _finite_float(data.get('y_min', MODEL_INIT_RANGES[model_name]['y_range'][0]), 'y_min'),
            _finite_float(data.get('y_max', MODEL_INIT_RANGES[model_name]['y_range'][1]), 'y_max'))
        lang = _language_code(data.get('lang', 'zh-CN'))
    except (TypeError, ValueError):
        return _error('参数格式无效')

    if not 1 <= frames <= MAX_FRAMES:
        return _error(f'帧数须在 1-{MAX_FRAMES} 之间')
    if start_frame < 0:
        return _error('起始迭代不能为负')
    if start_frame + frames > MAX_ITERATIONS:
        return _error(f'起始迭代加帧数不能超过 {MAX_ITERATIONS}')
    if len(params) != len(MODEL_CONFIGS[model_name]['params']):
        return _error('参数数量不匹配')
    if init_x_range[0] > init_x_range[1] or init_y_range[0] > init_y_range[1]:
        return _error('初始范围下限不能大于上限')

    limit = int(settings.get('request_rate_limit', 10))
    window = int(settings.get('request_rate_window_seconds', 60))
    if not access.check_rate_limit(ip, client_id, limit, window):
        access.record_denied(ip, client_id, 'rate_limit')
        return _error('请求过于频繁，请稍后再试', 429)

    _register_client(data, ip)
    client = clients.get(client_id)
    if client is None:
        return _error('在线客户端数量已达到上限', 429)
    payload = {
        'type': 'animate', 'model': model_name, 'params': params,
        'frames': frames, 'start_frame': start_frame,
        'init_x_range': init_x_range, 'init_y_range': init_y_range,
        'lang': lang,
    }
    try:
        task = task_queue.submit(payload, client_id, owner=auth.subject)
    except QueueLimitError as e:
        return _error(str(e), 429)
    log.info(f"→ 动画任务提交：{model_name}，{frames}帧（队列位置 {task_queue.queue_position(task.task_id)}）")
    return {
        'task_id': task.task_id, 'status': task.status,
        'queue_position': task_queue.queue_position(task.task_id),
        'paused': client is not None and client.status == 'paused',
    }


@app.get('/api/task/{task_id}')
async def task_status(task_id: str, request: Request):
    """查询任务状态、进度与结果；结果首次取走即交付"""
    snapshot = task_queue.get(task_id)
    if snapshot is None:
        return _error('任务不存在', 404)
    task = task_queue.get_task(task_id)
    if _authorize_task(request, task) is None:
        return _error('无权访问此任务', 403)

    if snapshot['status'] == 'completed' and not snapshot['delivered']:
        result = task_queue.get(task_id, include_result=True).get('result')
        if result is not None:
            # 结果同时写入客户端缓存（供刷新恢复），随后释放任务结果内存
            client_id = snapshot['client_id']
            if client_id:
                if snapshot['type'] == 'simulate':
                    client_cache.put(client_id, task_id, 'simulation', {
                        'type': 'simulation',
                        'viz_2d': result.get('viz_2d'),
                        'viz_3d': result.get('viz_3d'),
                        'model': result.get('model'),
                        'iterations': result.get('iterations'),
                    })
                else:
                    client_cache.put(client_id, task_id, 'animation', {
                        'type': 'animation',
                        'animation': result.get('animation'),
                        'model': result.get('model'),
                    })
            task_queue.mark_delivered(task_id)
            snapshot['result'] = result
    snapshot['queue_position'] = task_queue.queue_position(task_id)
    return snapshot


@app.post('/api/task/{task_id}/cancel')
async def cancel_task(task_id: str, request: Request):
    """客户端取消自己的任务"""
    guard = await _guard(request)
    if guard:
        return guard
    try:
        data = await request.json()
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    task = task_queue.get_task(task_id)
    if task is None:
        return _error('任务不存在', 404)
    if _authorize_task(request, task) is None:
        return _error('只能取消自己的任务', 403)
    ok, why = task_queue.cancel(task_id, by='client')
    if not ok:
        return _error(f'无法取消（{why}）')
    return {'success': True, 'state': why}


@app.post('/api/cleanup')
async def cleanup(request: Request):
    """清理客户端缓存与显存"""
    try:
        data = await request.json()
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        client_id = _client_id(data) if data.get('client_id') else ''
    except ValueError as e:
        return _error(str(e))
    if _authenticate(request, client_id) is None:
        return _error('缺少有效会话或访问密钥', 401)
    if client_id:
        client_cache.remove_client(client_id)
    success = True
    try:
        import gc as _gc
        _gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        success = False
    log.info(f"→ 清理缓存：{'完成' if success else '失败'}（{client_id[:8] if client_id else '全局'}）")
    return {'success': success, 'message': '缓存清理完成' if success else '缓存清理失败'}


@app.post('/api/restore')
async def restore(request: Request):
    """恢复客户端缓存的图表数据"""
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        client_id = _client_id(data) if data.get('client_id') else ''
    except ValueError as e:
        return _error(str(e))
    if _authenticate(request, client_id) is None:
        return _error('缺少有效会话或访问密钥', 401)
    include_animation = bool(data.get('include_animation', True))
    cached = client_cache.get(client_id, include_animation=include_animation)
    if cached is not None:
        log.info(f"→ 恢复缓存：客户端 {client_id[:8]}")
        return {'success': True, 'cached': cached}
    return {'success': False, 'cached': None}
