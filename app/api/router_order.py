from fastapi import APIRouter, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.broker.kis.kis_order import KISOrder
from app.broker.kis.enums import KRXOrderDivision, MarketType
from app.schemas.kis import DomesticStockOrderBuyResponse
from app.core.settings import settings

security = HTTPBearer()
router = APIRouter()

def get_kis_order() -> KISOrder:
    return KISOrder(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )


@router.post("/order/domestic-stock", response_model=DomesticStockOrderBuyResponse)
def buy_domestic_stock(
    stock_code: str,
    quantity: str,
    price: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    kis_order: KISOrder = Depends(get_kis_order),
) -> DomesticStockOrderBuyResponse:
    access_token = credentials.credentials
    
    
    # TODO: 일단은 KOSPI(KRX) 만 고려해서 order_type 설정하도록. 추후에 종목 코드에 따른 거래소 구분 로직 추가 필요.
    order_response = kis_order.buy_domestic_stock_by_cash(
        access_token=access_token,
        account_no=settings.KIS_ACCOUNT_NO,
        account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        order_type=KRXOrderDivision.MARKET.value,
        code=stock_code,
        quantity=quantity,
        price=price,
        exchange_type=MarketType.KRX.value
    )
    
    return DomesticStockOrderBuyResponse(**order_response) 