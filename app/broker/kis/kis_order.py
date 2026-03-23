import datetime
import httpx
from app.utils.logger import get_logger
from app.broker.kis.base import KISBase
import app.broker.kis.enums as kis_enums
from app.core.exceptions import KISOrderError
from app.core.settings import settings
from app.schemas.kis import DailyOrderExecutionResponse, ModifiableOrdersResponse, OrderResponse

logger = get_logger(__name__)

class KISOrder(KISBase):
    """
    _summary_
    - 주문 관련 기능 담당 클래스.
    """
    
    def __init__(self, appkey: str, appsecret:str, url: str = settings.kis_base_url):
        super().__init__(appkey, appsecret, url)
    
    
    def _check_within_3_months(self, start_date: str, end_date: str) -> bool:
        """주식일별 주문 체결 조회에서 3개월 이내 조회 여부를 판단하는 헬퍼 메서드."""
        start_dt = datetime.datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.datetime.strptime(end_date, "%Y%m%d")
        return (end_dt - start_dt).days <= 90
    
    
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
        exchange_type: str = kis_enums.EXCG_ID_DVSN_CD.KRX.value,
        endpoint: str = "/uapi/domestic-stock/v1/trading/order-cash"
    ) -> OrderResponse:
        url = f"{self.url}{endpoint}"
        
        # 거래 ID를 매수로 설정 (실제 운영에서는 종목별, 주문유형별로 세분화된 TR ID를 사용하는 것이 좋음)
        tr_id = kis_enums.TRID.DOMESTIC_STOCK_BUY.resolve(settings.TRADING_ENV == "paper")
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
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
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
        exchange_type: str = kis_enums.EXCG_ID_DVSN_CD.KRX.value,
        endpoint: str = "/uapi/domestic-stock/v1/trading/order-cash"
    ) -> OrderResponse:
        url = f"{self.url}{endpoint}"
        
        # 거래 ID를 매도로 설정 (실제 운영에서는 종목별, 주문유형별로 세분화된 TR ID를 사용하는 것이 좋음)
        tr_id = kis_enums.TRID.DOMESTIC_STOCK_SELL.resolve(settings.TRADING_ENV == "paper")
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id
        )

        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "PDNO": stock_code,
            "SLL_TYPE": kis_enums.SLL_TYPE.NORMAL.value,
            "ORD_DVSN": order_type,
            "ORD_QTY": quantity,
            "ORD_UNPR": price,
            "CNDT_PRIC": "",
            "EXCG_ID_DVSN_CD": exchange_type
        }
        logger.info(f"주식 매도 주문 요청 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {quantity} | 가격 : {price}")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
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
    async def modify_order_by_cash(
        self, 
        access_token: str, 
        account_no: str, 
        account_product_code: str, 
        krx_fwdg_ord_orgno: str,
        order_no: str,
        order_type: str, 
        revise_cancel_type: str,
        quantity: str,
        revise_price: str,
        qty_all_order_yn: str,
        exchange_type: str = kis_enums.EXCG_ID_DVSN_CD.KRX.value,
        endpoint: str ="/uapi/domestic-stock/v1/trading/order-rvsecncl"
    ) -> OrderResponse:
        url = f"{self.url}{endpoint}"
        tr_id = kis_enums.TRID.DOMESTIC_STOCK_MODIFY.resolve(settings.TRADING_ENV == "paper")
        
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
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
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
    # NOTE: 해당 함수는 모의투자 도메인을 지원하지 않으므로 Live 환경에서만 사용할 것.
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
        
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("rt_cd") != "0":
                raise KISOrderError(
                message=data.get("msg1", "정정/취소 가능 주문 조회 실패"),
                status_code=400,
                error_code=data.get("msg_cd"),
            )
            
            logger.info(f"정정/취소 가능 주문 조회 성공 : {self.url}{endpoint} | 조회구분1 : {inquire_div1} | 조회구분2 : {inquire_div2} | 조회된 주문 수 : {len(data.get('output', []))}")
            return ModifiableOrdersResponse(**data)
        except httpx.HTTPError as e:
            logger.error(f"정정/취소 가능 주문 조회 실패: {e}")
            raise KISOrderError("정정/취소 가능 주문 조회 중 오류가 발생했습니다.")
    
    
    # ⚙️ 주식일별 주문 체결 조회
    async def get_daily_order_executions(
        self,
        access_token: str,
        account_no: str,
        account_product_code: str,
        start_date: str,
        end_date: str,
        sell_buy_div: str = kis_enums.SLL_BUY_DVSN_CD.ALL.value,
        stock_code: str = "",
        broker_org_no: str = "",
        broker_order_no: str = "",
        ccld_div: str = kis_enums.CCDL_DVSN_CD.ALL.value,
        inquire_div: str = kis_enums.INQR_DVSN.DESC.value,
        inquire_div_1: str = kis_enums.INQR_DVSN_1.ALL.value,
        inquire_div_3: str = kis_enums.INQR_DVSN_3.ALL.value,
        exchange_type: str = kis_enums.EXCG_ID_DVSN_CD.KRX.value,
        endpoint: str = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
    ) -> DailyOrderExecutionResponse:
        url = f"{self.url}{endpoint}"
        curr_date = datetime.datetime.now().strftime("%Y%m%d")
        
        # 1. 조회 조건 설정에 따른 tr_id 결정
        within_3_months = self._check_within_3_months(start_date, end_date)
        if curr_date <= end_date and within_3_months:
            tr_id = kis_enums.TRID.DAILY_CCDL_RECENT.resolve(settings.TRADING_ENV == "paper")
        else:
            tr_id = kis_enums.TRID.DAILY_CCDL_OLD.resolve(settings.TRADING_ENV == "paper")
        
        
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id
        )
        
        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "INQR_STRT_DT": start_date,
            "INQR_END_DT": end_date,
            "SLL_BUY_DVSN_CD": sell_buy_div,
            "PDNO": stock_code,
            "ORG_GNO_BRNO": broker_org_no,
            "ODNO": broker_order_no,
            "CCLD_DVSN": ccld_div,
            "INQR_DVSN": inquire_div,
            "INQR_DVSN_1": inquire_div_1,
            "INQR_DVSN_3": inquire_div_3,
            "EXCG_ID_DVSN_CD": exchange_type,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers, params=payload)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("rt_cd") != "0":
                raise KISOrderError(
                message=data.get("msg1", "주식일별 주문 체결 조회 실패"),
                status_code=400,
                error_code=data.get("msg_cd"),
            )
            
            logger.info(f"주식일별 주문 체결 조회 성공 : {self.url}{endpoint} | 조회일자 : {start_date} ~ {end_date} | 조회된 체결 수 : {len(data.get('output1', []))}")
            return DailyOrderExecutionResponse(**data)
        except httpx.HTTPError as e:
            logger.error(f"주식일별 주문 체결 조회 실패: {e}")
            raise KISOrderError("주식일별 주문 체결 조회 중 오류가 발생했습니다.")