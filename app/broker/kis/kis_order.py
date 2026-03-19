import httpx
from app.utils.logger import get_logger
from app.broker.kis.base import KISBase
from app.broker.kis.enums import TradingType, MarketType, SellType
from app.core.exceptions import KISOrderError
from app.core.settings import settings
from app.schemas.kis import DomesticStorkOrderResponse

logger = get_logger(__name__)

class KISOrder(KISBase):
    """
    _summary_
    - 주문 관련 기능 담당 클래스.
    """
    
    def __init__(self, appkey: str, appsecret:str, url: str = settings.kis_base_url):
        super().__init__(appkey, appsecret, url)
    
    
    # ⚙️ 국내주식 현금 매수 주문 요청
    async def buy_domestic_stock_by_cash(
        self, 
        access_token: str, 
        account_no: str, 
        account_product_code: str, 
        order_type: str, 
        stock_code: str, 
        quantity: int, 
        price: int = 0,
        exchange_type: str = MarketType.KRX,
        endpoint: str = "/uapi/domestic-stock/v1/trading/order-cash"
    ) -> DomesticStorkOrderResponse:
        url = f"{self.url}{endpoint}"
        
        # 거래 ID를 매수로 설정 (실제 운영에서는 종목별, 주문유형별로 세분화된 TR ID를 사용하는 것이 좋음)
        tr_id = TradingType.DOMESTIC_STOCK_BUY.resolve(settings.TRADING_ENV == "paper")
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id
        )

        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "PDNO": stock_code,
            # "SLL_TYPE": "01",
            "ORD_DVSN": order_type,
            "ORD_QTY": quantity,
            "ORD_UNPR": price,
            "CNDT_PRIC": "",
            "EXCG_ID_DVSN_CD": exchange_type
        }
        logger.info(f"주식 매수 주문 요청 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {quantity} | 가격 : {price}")
        
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("rt_cd") != "0":
                raise KISOrderError(
                message=data.get("msg1", "주식 매수 주문 실패"),
                status_code=400,
                error_code=data.get("msg_cd"),
            )
            logger.info(f"주식 매수 주문 체결 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {quantity} | 가격 : {price} | 주문번호 : {data.get('ODNO')}")
            
            return DomesticStorkOrderResponse(**data)
        except httpx.HTTPError as e:
            logger.error(f"주식 매수 주문 체결 실패: {e}")
            raise KISOrderError("주식 매수 주문 중 오류가 발생했습니다.")
    
    
    # ⚙️ 국내주식 현금 매도 주문 요청
    async def sell_domestic_stock_by_cash(
        self, 
        access_token: str, 
        account_no: str, 
        account_product_code: str, 
        order_type: str, 
        stock_code: str, 
        quantity: int, 
        price: int = 0,
        exchange_type: str = MarketType.KRX,
        endpoint: str = "/uapi/domestic-stock/v1/trading/order-cash"
    ) -> DomesticStorkOrderResponse:
        url = f"{self.url}{endpoint}"
        
        # 거래 ID를 매도로 설정 (실제 운영에서는 종목별, 주문유형별로 세분화된 TR ID를 사용하는 것이 좋음)
        tr_id = TradingType.DOMESTIC_STOCK_SELL.resolve(settings.TRADING_ENV == "paper")
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id
        )

        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "PDNO": stock_code,
            "SLL_TYPE": SellType.NORMAL.values,
            "ORD_DVSN": order_type,
            "ORD_QTY": quantity,
            "ORD_UNPR": price,
            "CNDT_PRIC": "",
            "EXCG_ID_DVSN_CD": exchange_type
        }
        logger.info(f"주식 매도 주문 요청 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {quantity} | 가격 : {price}")
        
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("rt_cd") != "0":
                raise KISOrderError(
                message=data.get("msg1", "주식 매도 주문 실패"),
                status_code=400,
                error_code=data.get("msg_cd"),
            )
                
            logger.info(f"주식 매도 주문 체결 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {quantity} | 가격 : {price} | 주문번호 : {data.get('ODNO')}")
            return DomesticStorkOrderResponse(**data)
        
        except httpx.HTTPError as e:
            logger.error(f"주식 매도 주문 체결 실패: {e}")
            raise KISOrderError("주식 매도 주문 중 오류가 발생했습니다.")
        