from __future__ import annotations
 
import redis.asyncio as redis
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from app.utils.logger import get_logger

logger = get_logger(__name__)



class LockAcquisitionError(Exception):
    """분산 락 획득 실패 예외"""
    
    def  __init__(self, key: str, message: str | None = None) -> None:
        self.key = key
        super().__init__(message or f"분산락 획득 실패: key={key}")



# ⚙️ 분산락 획득(저수준)
async def acquire_lock(redis_client: redis.Redis, key: str, ttl_seconds: int) -> bool:
    """
    Redis 기반 분산락 획득
    - SET NX EX 단일 명령으로 원자적 획득(다른 인스턴스가 동시에 락을 획득하는 것을 방지)
    - 획득 성공: True / 이미 잠겨있으면: False
    - TTL은 비정상 종료 시의 안전망 (정상 흐름에서는 release_lock으로 해제)
    """
    acquired = await redis_client.set(key, "1", ex=ttl_seconds, nx=True)
    return bool(acquired)


# ⚙️ 분산락 해제 (저수준)
async def release_lock(redis_client: redis.Redis, key: str) -> None:
    """
    Redis 기반 분산락 해제
    - 단순 DELETE
    - 키가 없어도 에러 없이 통과
    """
    await redis_client.delete(key)


# ⚙️ 분산락 컨텍스트 매니저 (메인 인터페이스)
@asynccontextmanager
async def distributed_lock(
    redis_client: redis.Redis,
    key: str,
    ttl_seconds: int,
) -> AsyncIterator[None]:
    """
    분산락 컨텍스트 매니저
    - 정상 종료/예외 모두 release 보장
    - 획득 실패 시 LockAcquisitionError raise
    
    사용 예:
        async with distributed_lock(redis_client, "lock:rebalance:monthly", ttl_seconds=300):
            await do_long_running_task()
    """
    acquired = await acquire_lock(redis_client, key, ttl_seconds)
    if not acquired:
        raise LockAcquisitionError(key=key)
    
    try:
        yield
    finally:
        try:
            await release_lock(redis_client, key)
        except Exception as e:
            # release 실패는 치명적이지 않음 (TTL로 자연 해제됨). 로그만 남기고 계속 진행
            logger.warning(f"분산락 release 실패. key={key}, error={e}")