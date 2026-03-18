import httpx
from app.utils.logger import get_logger
from app.broker.kis.base import KISBase
from app.core.exceptions import KisAuthError
from app.core.settings import settings

logger = get_logger(__name__)

class KISOrder(KISBase):
    """
    _summary_
     - 주문 관련 기능 담당 클래스.
    """
    
    def __init__(self, appkey: str, appsecret:str, url: str = settings.kis_base_url):
        super().__init__(appkey, appsecret, url)
    
    
    # ⚙️ KIS API로부터 주식 주문 요청
    def order_domestic_stock_by_cash(self, access_token: str, account_no: str, account_product_code: str, order_type: str, code: str, quantity: int, price: int = 0, endpoint: str = "/uapi/domestic-stock/v1/trading/order-cash") -> dict:
        url = f"{self.url}{endpoint}"
        
        headers = self.build_headers(
            access_token=access_token,
            tr_id="VTTC0802R" if settings.TRADING_ENV == "paper" else "TTTC0802R"
        )
        
        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "ORD_DVSN": order_type,
            "PDNO": code,
            "ORD_QTY": quantity,
            "ORD_UNPR": price,
            "PRCS_DVSN": "00",
            "ALGO_ODR_TP_CD": "",
            "ALGO_PWD": "",
        }
        
        logger.info(f"주식 주문 요청 : {self.url}{endpoint} | payload={payload}")
        
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") != "0":
                raise KisAuthError(f"KIS API Error: {data.get('msg1')}")
            return data
        except httpx.HTTPError as e:
            logger.error(f"주식 주문 실패: {e}")
            raise KisAuthError("주식 주문 중 오류가 발생했습니다.")