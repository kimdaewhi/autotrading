import asyncio

from app.broker.kis.kis_auth import KISAuth
from app.broker.kis.kis_order import KISOrder
from app.worker.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.repository.order_repository import get_order_by_id
from app.core.enums import ORDER_STATUS
from app.core import settings
from app.utils.logger import get_logger



logger = get_logger(__name__)

TRACKING_TARGET_STATUSES = {
    ORDER_STATUS.REQUESTED,
    ORDER_STATUS.ACCEPTED,
    ORDER_STATUS.PARTIAL_FILLED,
}

# 주문 상태 중에서 최종 상태(체결 완료, 주문 실패, 주문 취소 등)로 간주되는 상태 집합
TERMINAL_STATUSES = {
    ORDER_STATUS.FAILED,
    ORDER_STATUS.FILLED,
    ORDER_STATUS.CANCELED,
}


@celery_app.task(name="app.worker.tasks_order_status.process_order_status")
def process_order_status(order_id: str) -> None:
    logger.info(f"주문 상태 추적 큐 등록. order_id : {order_id}")
    asyncio.run(_process_order_status(order_id))


async def _process_order_status(order_id: str) -> None:
    order_pk = None
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. 주문 조회
            order = await get_order_by_id(db, order_id)
            if order is None:
                logger.error(f"DB 조회 실패 - 주문이 존재하지 않습니다. order_id : {order_id}")
                return
            order_pk = order.id
            
            # 2. 해당 주문이 추적 대상 상태인지 확인
            if ORDER_STATUS(order.status) not in TRACKING_TARGET_STATUSES:
                logger.info(f"주문 상태 추적 대상 아님. order_id : {order_pk}, status : {order.status}")
                return

            # 3. 주문 번호 확인
            if not order.broker_order_no:
                logger.info(f"주문 번호 존재하지 않음 - 주문 추적 불가. order_id : {order_pk}")
                return
            
            # 4 인증 / 서비스 생성
            auth = KISAuth(
                appkey=settings.KIS_APP_KEY,
                appsecret=settings.KIS_APP_SECRET,
                url=f"{settings.kis_base_url}",
            )
            trade_service = trade_service(kis_order=KISOrder(
                appkey=settings.KIS_APP_KEY,
                appsecret=settings.KIS_APP_SECRET,
                url=f"{settings.kis_base_url}",
            ))
            
            token_response = await auth.get_access_token()
            access_token = token_response.access_token
            
            # 5. 주문 조회 API 호출
        except Exception as e:
            await db.rollback()
            logger.error(f"주문 상태 추적 실패. order_id : {order_pk or order_id}, error : {str(e)}")
            return