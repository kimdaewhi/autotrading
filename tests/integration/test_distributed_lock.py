"""
⭐ 분산락 유틸 통합테스트

실제 Redis(localhost:6379)에 연결하여 분산락 동작을 검증한다.
    - acquire/release 기본 동작
    - 동시 호출 시 1회만 성공
    - TTL 만료 후 재획득 가능
    - 컨텍스트 매니저: 정상 종료 시 release
    - 컨텍스트 매니저: 예외 발생 시에도 release
    - 획득 실패 시 LockAcquisitionError raise

실행 방법:
    pytest tests/integration/test_distributed_lock.py -v -s

주의:
    - 실제 Redis 서버가 localhost:6379에 떠있어야 한다
    - 테스트용 키는 'test:lock:*' prefix를 사용한다
"""

import asyncio
import pytest
import redis.asyncio as redis

from app.core.settings import settings
from app.utils.distributed_lock import (
    LockAcquisitionError,
    acquire_lock,
    distributed_lock,
    release_lock,
)


TEST_KEY_PREFIX = "test:lock"


# ── Fixtures ──

@pytest.fixture
async def redis_client():
    """테스트용 Redis 클라이언트"""
    client = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
    yield client
    # 테스트 종료 시 테스트 키 모두 정리
    keys = await client.keys(f"{TEST_KEY_PREFIX}:*")
    if keys:
        await client.delete(*keys)
    await client.close()


# ── 저수준 함수 테스트 ──

class TestAcquireRelease:
    """acquire_lock / release_lock 저수준 동작 검증"""
    
    @pytest.mark.asyncio
    async def test_acquire_success_when_key_not_exists(self, redis_client):
        """키가 없을 때 락 획득 성공"""
        key = f"{TEST_KEY_PREFIX}:basic_acquire"
        
        acquired = await acquire_lock(redis_client, key, ttl_seconds=10)
        
        assert acquired is True
        # Redis에 실제로 키가 들어갔는지 확인
        value = await redis_client.get(key)
        assert value is not None
    
    @pytest.mark.asyncio
    async def test_acquire_fails_when_already_locked(self, redis_client):
        """이미 잠긴 키에 대해 두 번째 acquire는 실패"""
        key = f"{TEST_KEY_PREFIX}:double_acquire"
        
        first = await acquire_lock(redis_client, key, ttl_seconds=10)
        second = await acquire_lock(redis_client, key, ttl_seconds=10)
        
        assert first is True
        assert second is False
    
    @pytest.mark.asyncio
    async def test_release_removes_key(self, redis_client):
        """release 후 키가 사라지는지 확인"""
        key = f"{TEST_KEY_PREFIX}:release_basic"
        
        await acquire_lock(redis_client, key, ttl_seconds=10)
        await release_lock(redis_client, key)
        
        value = await redis_client.get(key)
        assert value is None
    
    @pytest.mark.asyncio
    async def test_release_nonexistent_key_does_not_raise(self, redis_client):
        """존재하지 않는 키 release는 에러 없이 통과"""
        key = f"{TEST_KEY_PREFIX}:nonexistent"
        
        # 예외 없이 통과해야 함
        await release_lock(redis_client, key)
    
    @pytest.mark.asyncio
    async def test_acquire_after_release(self, redis_client):
        """release 후 다시 acquire 가능"""
        key = f"{TEST_KEY_PREFIX}:reacquire"
        
        first = await acquire_lock(redis_client, key, ttl_seconds=10)
        await release_lock(redis_client, key)
        second = await acquire_lock(redis_client, key, ttl_seconds=10)
        
        assert first is True
        assert second is True


# ── TTL 검증 ──

class TestTTL:
    """TTL 만료 동작 검증"""
    
    @pytest.mark.asyncio
    async def test_ttl_expiration_releases_lock(self, redis_client):
        """TTL 만료 후 락이 자동 해제되어 재획득 가능"""
        key = f"{TEST_KEY_PREFIX}:ttl_expire"
        
        # TTL 1초로 짧게 설정
        first = await acquire_lock(redis_client, key, ttl_seconds=1)
        assert first is True
        
        # 1.5초 대기 (TTL 만료 보장)
        await asyncio.sleep(1.5)
        
        second = await acquire_lock(redis_client, key, ttl_seconds=10)
        assert second is True, "TTL 만료 후 재획득 실패"


# ── 컨텍스트 매니저 테스트 ──

class TestDistributedLockContextManager:
    """distributed_lock 컨텍스트 매니저 동작 검증"""
    
    @pytest.mark.asyncio
    async def test_normal_completion_releases_lock(self, redis_client):
        """정상 종료 시 락이 release 됨"""
        key = f"{TEST_KEY_PREFIX}:ctx_normal"
        
        async with distributed_lock(redis_client, key, ttl_seconds=10):
            # 락이 잡혀 있는 상태
            value = await redis_client.get(key)
            assert value is not None
        
        # 컨텍스트 빠져나오면 락 해제됨
        value_after = await redis_client.get(key)
        assert value_after is None, "정상 종료 후 락이 release 되지 않음"
    
    @pytest.mark.asyncio
    async def test_exception_releases_lock(self, redis_client):
        """예외 발생 시에도 락이 release 됨 (★ recovery 버그 픽스 검증 시나리오)"""
        key = f"{TEST_KEY_PREFIX}:ctx_exception"
        
        with pytest.raises(ValueError, match="intentional"):
            async with distributed_lock(redis_client, key, ttl_seconds=10):
                raise ValueError("intentional")
        
        # 예외 발생했어도 락은 풀려있어야 함
        value_after = await redis_client.get(key)
        assert value_after is None, "예외 발생 시 락이 release 되지 않음"
    
    @pytest.mark.asyncio
    async def test_acquisition_failure_raises(self, redis_client):
        """이미 잠긴 키에 대한 컨텍스트 진입은 LockAcquisitionError"""
        key = f"{TEST_KEY_PREFIX}:ctx_acquisition_fail"
        
        # 먼저 락 점유
        await acquire_lock(redis_client, key, ttl_seconds=10)
        
        # 두 번째 진입은 실패해야 함
        with pytest.raises(LockAcquisitionError) as exc_info:
            async with distributed_lock(redis_client, key, ttl_seconds=10):
                pytest.fail("진입하면 안 됨")
        
        assert exc_info.value.key == key
    
    @pytest.mark.asyncio
    async def test_sequential_lock_usage(self, redis_client):
        """컨텍스트 매니저 연속 사용 시 매번 정상 동작"""
        key = f"{TEST_KEY_PREFIX}:ctx_sequential"
        
        for i in range(3):
            async with distributed_lock(redis_client, key, ttl_seconds=10):
                pass
            # 매번 release 되어 다음 iteration이 가능해야 함
        
        # 마지막에도 키가 남아있지 않음
        value = await redis_client.get(key)
        assert value is None


# ── 동시성 시나리오 ──

class TestConcurrency:
    """동시 호출 시 mutual exclusion 검증 (#16 회귀 테스트 항목)"""
    
    @pytest.mark.asyncio
    async def test_concurrent_acquire_only_one_succeeds(self, redis_client):
        """동시에 여러 worker가 락 시도 시 1개만 성공"""
        key = f"{TEST_KEY_PREFIX}:concurrent_acquire"
        
        # 10개 worker가 동시에 같은 락 시도
        results = await asyncio.gather(
            *[acquire_lock(redis_client, key, ttl_seconds=10) for _ in range(10)]
        )
        
        success_count = sum(1 for r in results if r is True)
        assert success_count == 1, f"동시 호출 10건 중 {success_count}건 성공 (1건이어야 함)"
    
    @pytest.mark.asyncio
    async def test_concurrent_context_manager_one_runs(self, redis_client):
        """동시 컨텍스트 매니저 진입 시 1개만 진입, 나머지는 LockAcquisitionError"""
        key = f"{TEST_KEY_PREFIX}:concurrent_ctx"
        execution_count = 0
        
        async def task():
            nonlocal execution_count
            try:
                async with distributed_lock(redis_client, key, ttl_seconds=10):
                    execution_count += 1
                    await asyncio.sleep(0.5)  # 실행 중 다른 worker 진입 시도
                return "success"
            except LockAcquisitionError:
                return "lock_failed"
        
        results = await asyncio.gather(*[task() for _ in range(5)])
        
        assert execution_count == 1, f"동시 진입 5건 중 {execution_count}건 실행 (1건이어야 함)"
        assert results.count("success") == 1
        assert results.count("lock_failed") == 4