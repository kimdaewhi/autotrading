from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.enums import OrderType
from app.broker.kis.kis_order import KISOrder
from app.broker.kis.enums import KRXOrderDivision, MarketType
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

# 국내주식 현금 매수 체결 요청
@router.post("/domestic-stock/buy", response_model=OrderResponse)
async def buy_domestic_stock(
    stock_code: str = Query(..., description="종목 코드 (예: 삼성전자 005930)"),
    quantity: str = Query(default="0", description="주문 수량"),
    order_type: OrderType = Query(default=OrderType.MARKET, description="주문 유형 (시장가: market, 지정가: limit)"),
    price: str = Query(default="0", description="시장가 주문인 경우 0으로 설정"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    kis_order: KISOrder = Depends(get_kis_order),
) -> OrderResponse:
    
    access_token = credentials.credentials
    
    if order_type == OrderType.MARKET:
        # 시장가 주문인 경우 API 스펙에 따라 price 값을 0으로 설정하거나, 아예 price 필드를 생략해야 할 수도 있음. 실제 API 문서 확인 필요.
        order_mode = KRXOrderDivision.MARKET.value
        normalized_price = "0"
    elif order_type == OrderType.LIMIT:
        if price in ("0", "", None):
            raise HTTPException(status_code=400, detail="지정가 주문은 price 값이 필요합니다.")
        order_mode = KRXOrderDivision.LIMIT.value
        normalized_price = price
    else:
        raise HTTPException(status_code=400, detail="order_type market 또는 limit만 가능합니다.")
    
    # TODO: 일단은 KOSPI(KRX) 만 고려해서 order_type 설정하도록. 추후에 종목 코드에 따른 거래소 구분 로직 추가 필요.
    order_response = await kis_order.buy_domestic_stock_by_cash(
        access_token=access_token,
        account_no=settings.KIS_ACCOUNT_NO,
        account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        order_type=order_mode,
        stock_code=stock_code,
        quantity=quantity,
        price=normalized_price,
        exchange_type=MarketType.KRX.value
    )
    
    return order_response


# 국내 주식 현금 매도 체결 요청
@router.post("/domestic-stock/sell", response_model=OrderResponse)
async def sell_domestic_stock(
    stock_code: str = Query(..., description="종목 코드 (예: 삼성전자 005930)"),
    quantity: str = Query(default="0", description="주문 수량"),
    order_type: OrderType = Query(default=OrderType.MARKET, description="주문 유형 (시장가: market, 지정가: limit)"),
    price: str = Query(default="0", description="시장가 주문인 경우 0으로 설정"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    kis_order: KISOrder = Depends(get_kis_order),
) -> OrderResponse:
    
    access_token = credentials.credentials
    
    if order_type == OrderType.MARKET:
        # 시장가 주문인 경우 API 스펙에 따라 price 값을 0으로 설정하거나, 아예 price 필드를 생략해야 할 수도 있음. 실제 API 문서 확인 필요.
        order_mode = KRXOrderDivision.MARKET.value
        normalized_price = "0"
    elif order_type == OrderType.LIMIT:
        if price in ("0", "", None):
            raise HTTPException(status_code=400, detail="지정가 주문은 price 값이 필요합니다.")
        order_mode = KRXOrderDivision.LIMIT.value
        normalized_price = price
    else:
        raise HTTPException(status_code=400, detail="order_type market 또는 limit만 가능합니다.")
    
    order_response = await kis_order.sell_domestic_stock_by_cash(
        access_token=access_token,
        account_no=settings.KIS_ACCOUNT_NO,
        account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        order_type=order_mode,
        stock_code=stock_code,
        quantity=quantity,
        price=normalized_price,
        exchange_type=MarketType.KRX.value
    )
    
    return order_response