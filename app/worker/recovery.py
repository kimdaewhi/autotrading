from app.db.session import AsyncSessionLocal
from app.repository.order_repository import get_recoverable_submit_orders, get_recoverable_tracking_orders
from app.utils.logger import get_logger

logger = get_logger(__name__)


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