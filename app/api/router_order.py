from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.enums import OrderType
from app.broker.kis.kis_order import KISOrder
from app.services.trade_service import TradeService
from app.broker.kis.enums import ORD_DVSN_KRX, EXCG_ID_DVSN_CD
from app.schemas.kis import OrderResponse
from app.core.settings import settings

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
@router.post("/domestic-stock/buy", response_model=OrderResponse)
async def buy_domestic_stock(
    stock_code: str = Query(..., description="종목 코드 (예: 삼성전자 005930)"),
    quantity: str = Query(default="0", description="주문 수량"),
    order_type: OrderType = Query(default=OrderType.MARKET, description="주문 유형 (시장가: market, 지정가: limit)"),
    price: str = Query(default="0", description="시장가 주문인 경우 0으로 설정"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    trade_service: TradeService = Depends(get_trade_service),
) -> OrderResponse:
    # 1. 인증 정보에서 액세스 토큰 추출
    access_token = credentials.credentials
    
    # 2. 서비스 레이어를 통해 매수 주문 요청
    # # TODO: 일단은 KOSPI(KRX) 만 고려해서 order_type 설정하도록. 추후에 종목 코드에 따른 거래소 구분 로직 추가 필요.
    # order_response = await trade_service.buy_domestic_stock(
    #     access_token=access_token,
    #     stock_code=stock_code,
    #     quantity=quantity,
    #     order_type=order_type,
    #     price=price
    # )
    
    # return order_response


# ⚙️ 국내 주식 현금 매도 체결 요청
@router.post("/domestic-stock/sell", response_model=OrderResponse)
async def sell_domestic_stock(
    stock_code: str = Query(..., description="종목 코드 (예: 삼성전자 005930)"),
    quantity: str = Query(default="0", description="주문 수량"),
    order_type: OrderType = Query(default=OrderType.MARKET, description="주문 유형 (시장가: market, 지정가: limit)"),
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