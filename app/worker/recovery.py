import redis.asyncio as redis

from app.db.session import AsyncSessionLocal
from app.repository.order_repository import get_recoverable_submit_orders, get_recoverable_tracking_orders
from app.core.settings import settings
from app.utils.distributed_lock import LockAcquisitionError, distributed_lock
from app.utils.logger import get_logger

logger = get_logger(__name__)


RECOVERY_LOCK_KEY = "autotrading:recovery:startup"
RECOVERY_LOCK_TTL_SECONDS = 300  # 5분: 비정상 종료 시 안전망


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
    - 분산락으로 다중 인스턴스 동시 실행 방지
    - 작업 완료 시 즉시 락 해제 → 후속 인스턴스가 자신의 복구 대상을 즉시 처리 가능
    """
    redis_client = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
    try:
        try:
            async with distributed_lock(redis_client, RECOVERY_LOCK_KEY, ttl_seconds=RECOVERY_LOCK_TTL_SECONDS):
                await recover_submit_orders()
                await recover_tracking_orders()
        except LockAcquisitionError:
            logger.info("다른 인스턴스에서 복구 작업 수행 중입니다. 이번 인스턴스는 복구를 건너뜁니다.")
            return
    finally:
        await redis_client.close()