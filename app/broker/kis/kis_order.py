import httpx
from app.utils.logger import get_logger
from app.broker.kis.base import KISBase
from app.broker.kis.enums import TRID, EXCG_ID_DVSN_CD, SLL_TYPE
from app.core.exceptions import KISOrderError
from app.core.settings import settings
from app.schemas.kis import ModifiableOrdersResponse, OrderResponse

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
        exchange_type: str = EXCG_ID_DVSN_CD.KRX.value,
        endpoint: str = "/uapi/domestic-stock/v1/trading/order-cash"
    ) -> OrderResponse:
        url = f"{self.url}{endpoint}"
        
        # 거래 ID를 매수로 설정 (실제 운영에서는 종목별, 주문유형별로 세분화된 TR ID를 사용하는 것이 좋음)
        tr_id = TRID.DOMESTIC_STOCK_BUY.resolve(settings.TRADING_ENV == "paper")
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id
        )

        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "PDNO": stock_code,
            # "SLL_TYPE": "01", # 매도 유형은 매수 주문에서는 사용되지 않지만, API 스펙에 따라 필수로 포함해야 할 수도 있음. 실제 API 문서 확인 필요.
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
            logger.info(f"주식 매수 주문 체결 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {quantity} | 가격 : {price} | 주문번호 : {data.get("output", {}).get('ODNO')}")
            
            return OrderResponse(**data)
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
        exchange_type: str = EXCG_ID_DVSN_CD.KRX.value,
        endpoint: str = "/uapi/domestic-stock/v1/trading/order-cash"
    ) -> OrderResponse:
        url = f"{self.url}{endpoint}"
        
        # 거래 ID를 매도로 설정 (실제 운영에서는 종목별, 주문유형별로 세분화된 TR ID를 사용하는 것이 좋음)
        tr_id = TRID.DOMESTIC_STOCK_SELL.resolve(settings.TRADING_ENV == "paper")
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id
        )

        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "PDNO": stock_code,
            "SLL_TYPE": SLL_TYPE.NORMAL.value,
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
            
            logger.info(f"주식 매도 주문 체결 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {quantity} | 가격 : {price} | 주문번호 : {data.get("output", {}).get('ODNO')}")
            return OrderResponse(**data)
        
        except httpx.HTTPError as e:
            logger.error(f"주식 매도 주문 체결 실패: {e}")
            raise KISOrderError("주식 매도 주문 중 오류가 발생했습니다.")
    
    
    # ⚙️ 국내주식 매매 주문 정정/취소 요청
    def modify_order_by_cash(
        self, 
        access_token: str, 
        account_no: str, 
        account_product_code: str, 
        krx_fwdg_ord_orgno: str,
        order_no: str,
        order_type: str, 
        revise_cancel_type: str,
        quantity: int,
        revise_price: str,
        qty_all_order_yn: str,
        exchange_type: str = EXCG_ID_DVSN_CD.KRX.value,
        endpoint: str ="/uapi/domestic-stock/v1/trading/order-rvsecncl"
    ) -> OrderResponse:
        url = f"{self.url}{endpoint}"
        tr_id = TRID.DOMESTIC_STOCK_MODIFY.resolve(settings.TRADING_ENV == "paper")
        
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id
        )
        
        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "KRX_FWDG_ORD_ORGNO": krx_fwdg_ord_orgno,
            "ORGN_ODNO": order_no,
            "ORD_DVSN": order_type,
            "RVSE_CNCL_DVSN_CD": revise_cancel_type,
            "ORD_QTY": quantity,
            "ORD_UNPR": revise_price,
            "QTY_ALL_ORD_YN": qty_all_order_yn,
            "CNDT_PRIC": "",
            "EXCG_ID_DVSN_CD": exchange_type
        }
        
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("rt_cd") != "0":
                raise KISOrderError(
                message=data.get("msg1", "주식 주문 정정/취소 실패"),
                status_code=400,
                error_code=data.get("msg_cd"),
            )
            
            logger.info(f"주식 주문 정정/취소 성공 : {self.url}{endpoint} | 주문번호 : {order_no} | 정정/취소 유형 : {revise_cancel_type} | 수량 : {quantity} | 가격 : {revise_price}")
            return OrderResponse(**data)
        
        except httpx.HTTPError as e:
            logger.error(f"주식 주문 정정/취소 실패: {e}")
            raise KISOrderError("주식 주문 정정/취소 중 오류가 발생했습니다.")
    
    
    # ⚙️ 국내주식 현금 매매 주문 취소 가능 주문 조회
    def get_cancelable_cash_orders(
        self,
        access_token: str,
        account_no: str,
        account_product_code: str,
        inquire_div1: str = "0",
        inquire_div2: str = "0",
        endpoint: str = "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
    ) -> ModifiableOrdersResponse:
        url = f"{self.url}{endpoint}"
        tr_id = "TTTC0084R"             # 정정/취소 가능 주문 조회용 tr_id는 하나밖에 없으므로 환경 구분 없이 고정값 사용
        
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id
        )
        
        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": inquire_div1,
            "INQR_DVSN_2": inquire_div2
        }