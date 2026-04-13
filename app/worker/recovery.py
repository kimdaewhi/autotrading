import redis.asyncio as redis

from app.db.session import AsyncSessionLocal
from app.repository.order_repository import get_recoverable_submit_orders, get_recoverable_tracking_orders
from app.core.settings import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def acquire_recovery_lock(lock_key: str = "autotrading:recovery:startup", ttl_seconds: int = 30) -> bool:
    """
    재기동 복구 작업의 중복 실행 방지를 위한 분산 락 획득
    - 여러 worker 인스턴스가 동시에 시작될 때, 최초 1개 인스턴스만 복구 작업 수행
    """
    redis_client = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
    try:
        acquired = await redis_client.set(lock_key, "1", ex=ttl_seconds, nx=True)
        return bool(acquired)
    finally:
        await redis_client.close()


async def recover_submit_orders() -> None:
    """
    서버/워커 재기동 시 PENDING 주문을 다시 submit queue에 등록
    """
    from app.worker.tasks_order import process_order

    async with AsyncSessionLocal() as db:
        orders = await get_recoverable_submit_orders(db)

        if not orders:
            logger.info("submit 복구 대상 주문 없음")
            return

        for order in orders:
            process_order.delay(str(order.id))
            logger.warning(f"주문 제출 복구 재등록. order_id={order.id}, status={order.status}, created_at={order.created_at}")


async def recover_tracking_orders() -> None:
    """
    서버/워커 재기동 시 미종결 주문을 다시 tracking queue에 등록
    """
    # 순환참조 방지 위해 import 지연
    from app.worker.tasks_order_status import process_order_status
    
    async with AsyncSessionLocal() as db:
        orders = await get_recoverable_tracking_orders(db)
        
        if not orders:
            logger.info("복구 대상 주문 없음")
            return
        
        for order in orders:
            process_order_status.delay(str(order.id))
            logger.warning(f"주문 추적 복구 재등록. order_id={order.id}, status={order.status}, created_at={order.created_at}")


async def recover_all_orders() -> None:
    """
    재기동 시 복구 작업 진입점
    """
    lock_acquired = await acquire_recovery_lock()
    if not lock_acquired:
        logger.info("다른 인스턴스에서 복구 작업 수행 중입니다. 이번 인스턴스는 복구를 건너뜁니다.")
        return

    await recover_submit_orders()
    await recover_tracking_orders()