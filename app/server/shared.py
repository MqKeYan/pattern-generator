"""
共享模块
======
跨应用的共享实例和工具类。
避免 main.py 和 admin_app.py 互相导入。
"""
from starlette.staticfiles import StaticFiles as _StaticFiles

from .store import ResultStore
from .pool import PoolManager
from .collector import SystemCollector


class StaticFiles(_StaticFiles):
    """静态文件服务 - 忽略非 HTTP 请求，避免 WebSocket 触发的 AssertionError"""
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        await super().__call__(scope, receive, send)


# 共享实例（按依赖顺序创建）
store = ResultStore()
pool = PoolManager(store=store)
collector = SystemCollector(pool_manager=pool)
