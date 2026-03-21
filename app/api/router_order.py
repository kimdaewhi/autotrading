from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.core.enums import ORDER_TYPE, ORDER_STATUS
from app.broker.kis.enums import EXCG_ID_DVSN_CD
from app.utils.logger import get_logger

from app.broker.kis.kis_order import KISOrder
from app.services.trade_service import TradeService
from app.schemas.kis import OrderResponse

from app.db.session import get_db
from app.repository.order_repository import create_order
from app.worker.tasks_order import process_order


logger = get_logger(__name__)

security = HTTPBearer()
router = APIRouter()

def get_kis_order() -> KISOrder:
    return KISOrder(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )

def get_trade_service(kis_order: KISOrder = Depends(get_kis_order)) -> TradeService:
    return TradeService(kis_order=kis_order)


# ⚙️ 국내주식 현금 매수 체결 요청
@router.post("/domestic-stock/buy")
async def buy_domestic_stock(
    stock_code: str = Query(..., description="종목 코드 (예: 삼성전자 005930)"),
    quantity: int = Query(default=0, description="주문 수량"),
    order_type: ORDER_TYPE = Query(default=ORDER_TYPE.MARKET, description="주문 유형 (시장가: market, 지정가: limit)"),
    price: Decimal = Query(default=Decimal("0"), description="시장가 주문인 경우 0으로 설정"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> None:
    # 인증 정보에서 액세스 토큰 추출
    access_token = credentials.credentials
    
    
    # # TODO: 일단은 KOSPI(KRX) 만 고려해서 order_type 설정하도록. 추후에 종목 코드에 따른 거래소 구분 로직 추가 필요.
    # 1. 매수 체결 요청 레코드 생성 및 DB 저장
    logger.info(f"주문 생성 및 DB 저장 시작")
    order = await create_order(
        db=db,
        order_data = {
            "account_no": settings.KIS_ACCOUNT_NO,
            "account_product_code": settings.KIS_ACCOUNT_PRODUCT_CODE,
            
            "market": EXCG_ID_DVSN_CD.KRX.value,
            "stock_code": stock_code,
            "order_pos": "buy",
            "order_type": order_type.value,
            "order_price": Decimal(price),
            "order_qty": int(quantity),
            
            "status": ORDER_STATUS.PENDING.value,
        }
    )
    
    await db.commit()
    
    # 2. commit 이후 큐에 주문 처리 태스크 등록
    process_order.delay(str(order.id))
    logger.info(f"주문 생성 및 큐 적재 완료 : 주문 ID : {order.id}")
    
    return {
        "order_id": str(order.id),
        "status": order.status,
        "message": "주문 요청이 접수되었습니다."
    }


# ⚙️ 국내 주식 현금 매도 체결 요청
@router.post("/domestic-stock/sell", response_model=OrderResponse)
async def sell_domestic_stock(
    stock_code: str = Query(..., description="종목 코드 (예: 삼성전자 005930)"),
    quantity: str = Query(default="0", description="주문 수량"),
    order_type: ORDER_TYPE = Query(default=ORDER_TYPE.MARKET, description="주문 유형 (시장가: market, 지정가: limit)"),
    price: str = Query(default="0", description="시장가 주문인 경우 0으로 설정"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    trade_service: TradeService = Depends(get_trade_service),
) -> OrderResponse:
    # 1. 인증 정보에서 액세스 토큰 추출
    access_token = credentials.credentials
    
    # 2. 서비스 레이어를 통해 매도 주문 요청
    order_response = await trade_service.sell_domestic_stock(
        access_token=access_token,
        stock_code=stock_code,
        quantity=quantity,
        order_type=order_type,
        price=price
    )
    
    return order_response