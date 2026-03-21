import asyncio
from app.broker.kis.kis_auth import KISAuth
from app.broker.kis.kis_order import KISOrder
from app.db.session import AsyncSessionLocal
from app.worker.celery_app import celery_app

from app.services.trade_service import TradeService
from app.repository.order_repository import get_order_by_id, update_order_status

from app.core.enums import ORDER_STATUS, ORDER_TYPE
from app.core.settings import settings
from app.utils.logger import get_logger



logger = get_logger(__name__)

@celery_app.task(name="app.worker.tasks_order.process_order")
def process_order(order_id: str) -> None:
    # 여기서는 일단 호출 확인만
    logger.info(f"주문 메시지큐 등록 테스트 order_id={order_id}")
    
    asyncio.run(_process_order(order_id))


async def _process_order(order_id: str) -> None:
    async with AsyncSessionLocal() as db:
        try:
            # 1. DB에서 order_id 조회
            order = await get_order_by_id(db, order_id)
            if order is None:
                logger.error(f"DB 조회 실패 - 주문이 존재하지 않습니다. order_id : {order_id}")
                return
            order_pk = order.id # 만약 아래 작업에서 터진다면 order_id로 조회가 안되서 order_pk로 캐싱
            
            # 2. PENDING 상태 확인 및 PROCESSING 상태로 전이(다른 워커가 이미 처리 중인 경우에는 상태 업데이트 실패 처리)
            updated = await update_order_status(db=db, order_id=order_pk, expected_current_statuses=[ORDER_STATUS.PENDING], new_status=ORDER_STATUS.PROCESSING)
            if not updated:
                logger.warning(f"이미 다른 워커가 처리 중이거나 상태가 변경됨. order_id={order_id}")
                return

            await db.commit()
            
            # 3. access token 발급을 위한 인증 서비스 및 TradeService 인스턴스 생성
            auth = KISAuth(
                appkey=settings.KIS_APP_KEY, 
                appsecret=settings.KIS_APP_SECRET, 
                url=f"{settings.kis_base_url}"
            )
            trade_service = TradeService(kis_order=KISOrder(
                appkey=settings.KIS_APP_KEY, 
                appsecret=settings.KIS_APP_SECRET, 
                url=f"{settings.kis_base_url}"
                )
            )
            
            token_response = await auth.get_access_token()
            access_token = token_response.access_token
            
            # 4. Broker 주문 체결 API 요청
            if order.order_pos == "buy":
                service_result = await trade_service.buy_domestic_stock(
                    access_token=access_token,
                    stock_code=order.stock_code,
                    quantity=str(order.order_qty),
                    order_type=ORDER_TYPE(order.order_type),
                    price=str(order.order_price),
                )
                # TODO : 응답 전문, ODNO, 등등등 필요한 정보를 DB에 저장하는 작업 필요함... 장 열리면
            elif order.order_pos == "sell":
                service_result = await trade_service.sell_domestic_stock(
                    access_token=access_token,
                    stock_code=order.stock_code,
                    quantity=str(order.order_qty),
                    order_type=ORDER_TYPE(order.order_type),
                    price=str(order.order_price),
                )
            else:
                logger.error(f"알 수 없는 주문 유형 order_id : {order_id}")
                return
            
            # 5. 주문 결과에 따라 사후 처리(FILLED, PARTIAL_FILLED, FAILED, CANCELED 등)
            updated = await update_order_status(db=db, order_id=order_pk, expected_current_statuses=[ORDER_STATUS.PROCESSING], new_status=ORDER_STATUS.REQUESTED)
            if not updated:
                await db.rollback()
                logger.error(f"REQUESTED 상태 변경 실패. order_id : {order_pk}")
                return
            await db.commit()
            
            logger.info(f"주문 요청 성공. order_id={order_pk}")
            
            # 6. 주문 결과에 따라 사후 처리(FILLED, PARTIAL_FILLED, FAILED, CANCELED 등)
            
        except Exception as e:
            await db.rollback()
            
            await update_order_status(db=db, order_id=order_pk, expected_current_statuses=[ORDER_STATUS.PROCESSING, ORDER_STATUS.REQUESTED, ORDER_STATUS.ACCEPTED], new_status=ORDER_STATUS.FAILED)
            await db.commit()
            logger.error(f"주문 처리 실패. order_id={order_pk}, error={str(e)}")
            
            return