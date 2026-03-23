import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from app.db.session import dispose_async_engine

T = TypeVar("T")

_worker_loop: asyncio.AbstractEventLoop | None = None


def init_worker_runtime() -> asyncio.AbstractEventLoop:
    """
    Celery worker child process마다 하나의 event loop만 유지한다.
    task마다 asyncio.run()으로 loop를 새로 만들면 asyncpg 커넥션과 엔진이
    이전 loop에 묶인 상태로 남아 loop 충돌이 발생할 수 있다.
    """
    global _worker_loop
    
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
        
    return _worker_loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    loop = init_worker_runtime()
    return loop.run_until_complete(coro)


def shutdown_worker_runtime() -> None:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = None
        return
    
    loop = _worker_loop
    loop.run_until_complete(dispose_async_engine())
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()
    _worker_loop = None