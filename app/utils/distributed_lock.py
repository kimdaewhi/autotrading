"""
Redis 기반 분산락 유틸

여러 워커/인스턴스가 동일 작업을 동시에 수행하지 못하도록 mutual exclusion을 보장한다.

핵심 보장:
- 원자적 획득: SET NX EX 단일 명령 사용 (GET 후 SET 패턴의 race 방지)
- 자동 해제: 컨텍스트 매니저 사용 시 정상/예외 종료 모두 release
- 안전망 TTL: 워커 비정상 종료 시 락이 영구 점유되지 않도록 TTL 자동 만료

사용처:
- AuthService: KIS access token 동시 재발급 방지
- recovery.py: 다중 인스턴스 재기동 시 복구 작업 중복 실행 방지
- (예정) tasks_rebalance.py: 월 1회 리밸런싱 중복 실행 방지

설계 원칙 — 의도적으로 만들지 않은 것:
- owner token (UUID 소유권 검증)
    → 현 사용처 모두 작업시간 << TTL 이라 잘못된 release 위험 없음.
      작업 시간이 TTL을 초과할 수 있는 워크로드 추가 시 도입 검토.
- watchdog (TTL 자동 연장)
    → 동일 이유. 긴 작업 추가 시 도입 검토.
- 재시도 정책 (대기 후 재획득)
    → 호출처마다 정책이 달라 (기다림 vs 즉시 fail vs 건너뛰기)
      유틸에 넣지 않고 호출처가 LockAcquisitionError 처리.

TTL 설정 가이드:
- 작업 예상 시간의 2~3배를 권장 (안전 마진).
- 너무 짧으면: 작업 중 만료 → 다른 워커 진입 위험.
- 너무 길면: 비정상 종료 시 다음 시도까지 불필요한 대기.
"""

from __future__ import annotations
 
import redis.asyncio as redis
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from app.utils.logger import get_logger

logger = get_logger(__name__)



class LockAcquisitionError(Exception):
    """
    분산락 획득 실패 예외
    
    호출처는 이 예외를 잡아 컨텍스트에 맞는 정책을 적용한다:
    - 토큰 갱신: 다른 워커의 갱신 완료를 대기 (AuthService)
    - 재기동 복구: 그냥 건너뛰기 (recovery.py)
    - 리밸런싱: 다음 스케줄까지 대기 (예정)
    """
    
    def  __init__(self, key: str, message: str | None = None) -> None:
        self.key = key
        super().__init__(message or f"분산락 획득 실패: key={key}")



# ⚙️ 분산락 획득(저수준)
async def acquire_lock(redis_client: redis.Redis, key: str, ttl_seconds: int) -> bool:
    """
    Redis 기반 분산락 획득 (저수준)
    
    - SET NX EX 단일 명령으로 원자적 획득 (다른 인스턴스가 동시에 락을 획득하는 것을 방지)
    - 획득 성공: True / 이미 잠겨있으면: False
    - TTL은 비정상 종료 시의 안전망 (정상 흐름에서는 release_lock으로 해제)
    
    일반적인 사용은 distributed_lock 컨텍스트 매니저를 권장.
    이 저수준 함수는 컨텍스트 매니저로 표현하기 어려운 특수 케이스용.
    """
    acquired = await redis_client.set(key, "1", ex=ttl_seconds, nx=True)
    return bool(acquired)


# ⚙️ 분산락 해제 (저수준)
async def release_lock(redis_client: redis.Redis, key: str) -> None:
    """
    Redis 기반 분산락 해제 (저수준)
    
    - 단순 DELETE
    - 키가 없어도 에러 없이 통과 (이중 release, TTL 만료 후 release 등 안전)
    - owner 검증 없음: TTL 만료로 다른 워커가 잡은 락을 잘못 풀 가능성 존재.
      현재 모든 사용처는 작업시간 << TTL 이라 이 시나리오 발생하지 않음.
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
    분산락 컨텍스트 매니저 (메인 인터페이스)
    
    - 정상 종료/예외 모두 release 보장
    - 획득 실패 시 LockAcquisitionError raise (호출처가 정책 결정)
    - release 실패 시 로그만 남기고 통과 (TTL로 자연 해제되므로 치명적이지 않음)
    
    사용 예:
        async with distributed_lock(redis_client, "lock:rebalance:monthly", ttl_seconds=300):
            await do_long_running_task()
    
    주의:
    - ttl_seconds는 작업 예상 시간의 2~3배로 설정.
    - 같은 redis_client 인스턴스를 여러 곳에서 공유해도 안전 (락 키로 격리됨).
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
            # release 실패는 치명적이지 않음 (TTL로 자연 해제됨).
            # 여기서 raise하면 호출처의 정상 결과가 묻혀버리므로 로그만 남기고 통과.
            logger.warning(f"분산락 release 실패. key={key}, error={e}")