from fastapi import HTTPException

from app.broker.kis.enums import ORD_DVSN_KRX, EXCG_ID_DVSN_CD
from app.broker.kis.kis_order import KISOrder
from app.core.enums import OrderType
from app.core.settings import settings
from app.schemas.kis import OrderResponse


class TradeService:
    """
    _summary_
    - 실제 주문 로직을 담당하는 서비스 레이어 클래스.
    
    _description_
    - API 라우터에서는 이 클래스를 호출해서 주문 관련 비즈니스 로직을 처리하도록 구현.
    - 주문 체결 요청에 성공, 실패 보장, 트랜잭션 처리, 주문 유형에 따른 파라미터 변환 등 주문과 관련된 핵심 로직을 담당.
    """
    def __init__(self, kis_order: KISOrder):
        self.kis_order = kis_order
    
    
    # ⚙️ 주문 유형에 따른 API 파라미터 변환 로직을 private method로 관리
    def _resolve_order_params(self, order_type: OrderType, price: str) -> tuple[str, str]:
        if order_type == OrderType.MARKET:
            return ORD_DVSN_KRX.MARKET.value, "0"
        
        if order_type == OrderType.LIMIT:
            if price in ("0", "", None):
                raise HTTPException(status_code=400, detail="지정가 주문은 price 값이 필요합니다.")
            return ORD_DVSN_KRX.LIMIT.value, price
        
        raise HTTPException(status_code=400, detail="order_type market 또는 limit만 가능합니다.")
    
    
    # ⚙️ 국내 주식 현금 매수 체결 요청
    async def buy_domestic_stock(
        self,
        access_token: str,
        stock_code: str,
        quantity: str,
        order_type: OrderType,
        price: str = "0",
    ) -> OrderResponse:
        # 1. 주문 유형에 의한 파라미터 변환
        order_mode, normalized_price = self._resolve_order_params(order_type, price)

        return await self.kis_order.buy_domestic_stock_by_cash(
            access_token=access_token,
            account_no=settings.KIS_ACCOUNT_NO,
            account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
            order_type=order_mode,
            stock_code=stock_code,
            quantity=quantity,
            price=normalized_price,
            exchange_type=EXCG_ID_DVSN_CD.KRX.value,
        )
    
    
    # ⚙️ 국내 주식 현금 매도 체결 요청
    async def sell_domestic_stock(
        self,
        access_token: str,
        stock_code: str,
        quantity: str,
        order_type: OrderType,
        price: str = "0",
    ) -> OrderResponse:
        order_mode, normalized_price = self._resolve_order_params(order_type, price)

        return await self.kis_order.sell_domestic_stock_by_cash(
            access_token=access_token,
            account_no=settings.KIS_ACCOUNT_NO,
            account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
            order_type=order_mode,
            stock_code=stock_code,
            quantity=quantity,
            price=normalized_price,
            exchange_type=EXCG_ID_DVSN_CD.KRX.value,
        )