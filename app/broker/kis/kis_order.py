import asyncio
import datetime
from decimal import Decimal
import httpx
from app.core.constants import HTTP_RETRY_COUNT
from app.utils.logger import get_logger
from app.broker.kis.base import KISBase
import app.broker.kis.enums as kis_enums
from app.core.exceptions import KISOrderError
from app.core.settings import settings
from app.schemas.kis.kis import DailyOrderExecutionResponse, ModifiableOrdersResponse, OrderResponse

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
        # price 및 quantity는 API 스펙 상 문자열로 전달해야 하므로, 정수형으로 변환 후 문자열로 변환
        str_qty = str(int(quantity))
        str_price = str(int(Decimal(str(price)))) if price != 0 else "0"
        
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id
        )
        
        payload = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "PDNO": stock_code,
            "SLL_TYPE": "",
            "ORD_DVSN": order_type,
            "ORD_QTY": str_qty,
            "ORD_UNPR": str_price,
            "CNDT_PRIC": "",
            "EXCG_ID_DVSN_CD": exchange_type
        }
        # logger.info(f"주식 매수 주문 요청 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {str_qty} | 가격 : {str_price}")
        
        for attempt in range(HTTP_RETRY_COUNT):  # 최대 3회 재시도
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                if 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError(f"서버 오류: {resp.status_code}", request=resp.request, response=resp)
                resp.raise_for_status()
                break
            # RequestError, TimeoutException은 진짜 네트워크 문제
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == HTTP_RETRY_COUNT - 1:
                    # 최대 재시도 도달 시 원래 예외나 전용 KISOrderError로 변환해서 전달
                    raise KISOrderError(
                        message=f"주식 매수 주문 요청 실패: {e}",
                        status_code=500,
                        error_code=None,
                        rt_cd="ERROR",
                        msg_cd="NETWORK_ERROR",
                        msg1=f"주식 매수 주문 요청 실패: {e}",
                        payload={
                            "stage": "buy_domestic_stock_by_cash",
                            "error": str(e),
                        }
                    )
                await asyncio.sleep(0.5 * (attempt + 1))  # 지수 백오프 (0.5s, 1s, 1.5s)
            # HTTPStatusError는 4xx, 5xx 응답에 대한 예외이므로 응답 메시지 파싱 시도
            except httpx.HTTPStatusError as e:
                error_payload = None
                msg1 = f"주식 매수 주문 요청 실패: HTTP {e.response.status_code}"
                msg_cd = "BROKER_HTTP_ERROR"
                rt_cd = "ERROR"
                try:
                    error_payload = e.response.json()
                    rt_cd = error_payload.get("rt_cd", "ERROR")
                    msg_cd = error_payload.get("msg_cd", "BROKER_HTTP_ERROR")
                    msg1 = error_payload.get("msg1", msg1)
                except Exception:
                    error_payload = {
                        "status_code": e.response.status_code,
                        "response_text": e.response.text,
                    }
                if attempt == HTTP_RETRY_COUNT - 1:
                    raise KISOrderError(
                        message=msg1,
                        status_code=e.response.status_code,
                        error_code=msg_cd,
                        rt_cd=rt_cd,
                        msg_cd=msg_cd,
                        msg1=msg1,
                        payload={
                            "stage": "buy_domestic_stock_by_cash",
                            "status_code": e.response.status_code,
                            "response": error_payload,
                        },
                    )
                await asyncio.sleep(0.5 * (attempt + 1))
        
        data = resp.json()
        
        if data.get("rt_cd") != "0":
            raise KISOrderError(
                message=data.get("msg1", "주식 매수 주문 실패"),
                status_code=400,
                error_code=data.get("msg_cd"),
                rt_cd=data.get("rt_cd"),
                msg_cd=data.get("msg_cd"),
                msg1=data.get("msg1"),
                payload=data
            )
        order_no = data.get("output", {}).get("ODNO")
        logger.info(f"주식 매수 주문 요청 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {quantity} | 가격 : {price} | 주문번호 : {order_no}")
        
        return OrderResponse(**data)
    
    
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
        # price 및 quantity는 API 스펙 상 문자열로 전달해야 하므로, 정수형으로 변환 후 문자열로 변환
        str_qty = str(int(quantity))
        str_price = str(int(Decimal(str(price)))) if price != 0 else "0"
        
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
            "ORD_QTY": str_qty,
            "ORD_UNPR": str_price,
            "CNDT_PRIC": "",
            "EXCG_ID_DVSN_CD": exchange_type
        }
        # logger.info(f"주식 매도 주문 요청 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {str_qty} | 가격 : {str_price}")
        
        for attempt in range(HTTP_RETRY_COUNT):  # 최대 3회 재시도
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                if 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError(f"서버 오류: {resp.status_code}", request=resp.request, response=resp)
                resp.raise_for_status()
                break
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == HTTP_RETRY_COUNT - 1:
                    raise KISOrderError(
                        message=f"주식 매도 주문 요청 실패: {e}",
                        status_code=500,
                        error_code=None,
                        rt_cd="ERROR",
                        msg_cd="NETWORK_ERROR",
                        msg1=f"주식 매도 주문 요청 실패 : {e}",
                        payload={
                            "stage": "sell_domestic_stock_by_cash",
                            "error": str(e),
                        }
                    )
                await asyncio.sleep(0.5 * (attempt + 1))  # 지수 백오프 (0.5s, 1s, 1.5s)
            except httpx.HTTPStatusError as e:
                error_payload = None
                msg1 = f"주식 매도 주문 요청 실패: HTTP {e.response.status_code}"
                msg_cd = "BROKER_HTTP_ERROR"
                rt_cd = "ERROR"
                try:
                    error_payload = e.response.json()
                    rt_cd = error_payload.get("rt_cd", "ERROR")
                    msg_cd = error_payload.get("msg_cd", "BROKER_HTTP_ERROR")
                    msg1 = error_payload.get("msg1", msg1)
                except Exception:
                    error_payload = {
                        "status_code": e.response.status_code,
                        "response_text": e.response.text,
                    }
                if attempt == HTTP_RETRY_COUNT - 1:
                    raise KISOrderError(
                        message=msg1,
                        status_code=e.response.status_code,
                        error_code=msg_cd,
                        rt_cd=rt_cd,
                        msg_cd=msg_cd,
                        msg1=msg1,
                        payload={
                            "stage": "sell_domestic_stock_by_cash",
                            "status_code": e.response.status_code,
                            "response": error_payload,
                        },
                    )
                await asyncio.sleep(0.5 * (attempt + 1))
        
        data = resp.json()
        
        if data.get("rt_cd") != "0":
            raise KISOrderError(
            message=data.get("msg1", "주식 매도 주문 실패"),
                status_code=400,
                error_code=data.get("msg_cd"),
                rt_cd=data.get("rt_cd"),
                msg_cd=data.get("msg_cd"),
                msg1=data.get("msg1"),
                payload=data
            )
        order_no = data.get("output", {}).get("ODNO")
        logger.info(f"주식 매도 주문 요청 : {self.url}{endpoint} | 종목코드 : {stock_code} | 수량 : {quantity} | 가격 : {price} | 주문번호 : {order_no}")
        
        return OrderResponse(**data)
    
    
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
        endpoint: str = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
    ) -> OrderResponse:
        # 기본 데이터 셋업
        url = f"{self.url}{endpoint}"
        tr_id = kis_enums.TRID.DOMESTIC_STOCK_MODIFY.resolve(settings.TRADING_ENV == "paper")
        str_price = str(int(Decimal(str(revise_price)))) if revise_price != 0 else "0"
        
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
            "ORD_UNPR": str_price,
            "QTY_ALL_ORD_YN": qty_all_order_yn,
            "CNDT_PRIC": "",
            "EXCG_ID_DVSN_CD": exchange_type,
        }
        # logger.info(f"주식 주문 정정/취소 요청 데이터 : {payload}")
        # logger.info(f"주식 주문 정정/취소 요청 : {self.url}{endpoint} "f"| 원주문번호 : {order_no} | KRX전송주문조직번호 : {krx_fwdg_ord_orgno} "f"| 정정/취소구분 : {revise_cancel_type} | 수량 : {quantity} | 가격 : {revise_price}")
        
        for attempt in range(HTTP_RETRY_COUNT):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                if 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError(
                        f"서버 오류: {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("rt_cd") != "0":
                    raise KISOrderError(
                        message=data.get("msg1", "주식 주문 정정/취소 실패"),
                        status_code=400,
                        error_code=data.get("msg_cd"),
                        rt_cd=data.get("rt_cd"),
                        msg_cd=data.get("msg_cd"),
                        msg1=data.get("msg1"),
                        payload=data,
                    )
                logger.info(
                    f"주식 주문 정정/취소 성공 : {self.url}{endpoint} "
                    f"| 원주문번호 : {order_no} | 정정/취소 유형 : {revise_cancel_type} "
                    f"| 수량 : {quantity} | 가격 : {revise_price}"
                )
                return OrderResponse(**data)
            
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == HTTP_RETRY_COUNT - 1:
                    raise KISOrderError(
                        message=f"주식 주문 정정/취소 요청 실패: {e}",
                        status_code=500,
                        error_code=None,
                        rt_cd="ERROR",
                        msg_cd="NETWORK_ERROR",
                        msg1=f"주식 주문 정정/취소 요청 실패: {e}",
                        payload={
                            "stage": "modify_order_by_cash",
                            "error": str(e),
                        },
                    )
                await asyncio.sleep(0.5 * (attempt + 1))
            except httpx.HTTPStatusError as e:
                error_payload = None
                msg1 = f"주식 주문 정정/취소 요청 실패: HTTP {e.response.status_code}"
                msg_cd = "BROKER_HTTP_ERROR"
                rt_cd = "ERROR"
                try:
                    error_payload = e.response.json()
                    rt_cd = error_payload.get("rt_cd", "ERROR")
                    msg_cd = error_payload.get("msg_cd", "BROKER_HTTP_ERROR")
                    msg1 = error_payload.get("msg1", msg1)
                except Exception:
                    error_payload = {
                        "status_code": e.response.status_code,
                        "response_text": e.response.text,
                    }
                
                if attempt == HTTP_RETRY_COUNT - 1:
                    raise KISOrderError(
                        message=msg1,
                        status_code=e.response.status_code,
                        error_code=msg_cd,
                        rt_cd=rt_cd,
                        msg_cd=msg_cd,
                        msg1=msg1,
                        payload={
                            "stage": "modify_order_by_cash",
                            "status_code": e.response.status_code,
                            "response": error_payload,
                        },
                    )
                await asyncio.sleep(0.5 * (attempt + 1))
                raise KISOrderError("주식 주문 정정/취소 중 오류가 발생했습니다.")
    
    
    # ⚙️ 국내주식 매매 주문 취소 가능한 주문 리스트 조회
    # NOTE: 해당 함수는 모의투자 도메인을 지원하지 않으므로 Live 환경에서만 사용할 것.
    async def get_cancelable_cash_orders(
        self,
        access_token: str,
        account_no: str,
        account_product_code: str,
        inquire_div1: str = "0",
        inquire_div2: str = "0",
        endpoint: str = "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
    ) -> ModifiableOrdersResponse:
        if settings.TRADING_ENV == "paper":
            raise KISOrderError(
                message="정정/취소 가능 주문 조회는 모의투자를 지원하지 않습니다.",
                status_code=400,
                error_code="PAPER_NOT_SUPPORTED",
                rt_cd="ERROR",
                msg_cd="PAPER_NOT_SUPPORTED",
                msg1="정정/취소 가능 주문 조회는 모의투자를 지원하지 않습니다.",
                payload={
                    "stage": "get_cancelable_cash_orders",
                    "trading_env": settings.TRADING_ENV,
                }
            )
            
        url = f"{self.url}{endpoint}"
        tr_id = "TTTC0084R"
        
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
            "INQR_DVSN_2": inquire_div2,
        }
        
        for attempt in range(HTTP_RETRY_COUNT):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    
                if 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError(
                        f"서버 오류: {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                    
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("rt_cd") != "0":
                    raise KISOrderError(
                        message=data.get("msg1", "정정/취소 가능 주문 조회 실패"),
                        status_code=400,
                        error_code=data.get("msg_cd"),
                        rt_cd=data.get("rt_cd"),
                        msg_cd=data.get("msg_cd"),
                        msg1=data.get("msg1"),
                        payload=data,
                    )
                    
                logger.info(
                    f"정정/취소 가능 주문 조회 성공 : {self.url}{endpoint} "
                    f"| 조회구분1 : {inquire_div1} | 조회구분2 : {inquire_div2}"
                )
                return ModifiableOrdersResponse(**data)
            
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == HTTP_RETRY_COUNT - 1:
                    raise KISOrderError(
                        message=f"정정/취소 가능 주문 조회 실패: {e}",
                        status_code=500,
                        error_code=None,
                        rt_cd="ERROR",
                        msg_cd="NETWORK_ERROR",
                        msg1=f"정정/취소 가능 주문 조회 실패: {e}",
                        payload={
                            "stage": "get_cancelable_cash_orders",
                            "error": str(e),
                        },
                    )
                await asyncio.sleep(0.5 * (attempt + 1))
            except httpx.HTTPStatusError as e:
                error_payload = None
                msg1 = f"정정/취소 가능 주문 조회 실패: HTTP {e.response.status_code}"
                msg_cd = "BROKER_HTTP_ERROR"
                rt_cd = "ERROR"
                try:
                    error_payload = e.response.json()
                    rt_cd = error_payload.get("rt_cd", "ERROR")
                    msg_cd = error_payload.get("msg_cd", "BROKER_HTTP_ERROR")
                    msg1 = error_payload.get("msg1", msg1)
                except Exception:
                    error_payload = {
                        "status_code": e.response.status_code,
                        "response_text": e.response.text,
                    }
                if attempt == HTTP_RETRY_COUNT - 1:
                    raise KISOrderError(
                        message=msg1,
                        status_code=e.response.status_code,
                        error_code=msg_cd,
                        rt_cd=rt_cd,
                        msg_cd=msg_cd,
                        msg1=msg1,
                        payload={
                            "stage": "get_cancelable_cash_orders",
                            "status_code": e.response.status_code,
                            "response": error_payload,
                        },
                    )
                await asyncio.sleep(0.5 * (attempt + 1))
    
    
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
        
        for attempt in range(HTTP_RETRY_COUNT):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, headers=headers, params=payload)
                
                if 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError(
                        message=f"Server error: {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("rt_cd") != "0":
                    raise KISOrderError(
                        message=data.get("msg1", "주식일별 주문 체결 조회 실패"),
                        status_code=400,
                        error_code=data.get("msg_cd"),
                        rt_cd=data.get("rt_cd"),
                        msg_cd=data.get("msg_cd"),
                        msg1=data.get("msg1"),
                        payload=data
                    )
                
                logger.info(
                    f"주식일별 주문 체결 조회 성공 : {self.url}{endpoint} | 조회일자 : {start_date} ~ {end_date} | 조회된 주문 수 : {len(data.get('output1', []))}"
                )
                return DailyOrderExecutionResponse(**data)
            
            except (httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response is not None:
                    if 400 <= e.response.status_code < 500:
                        raise KISOrderError(
                            message=f"주식일별 주문 체결 조회 실패: {e}",
                            status_code=e.response.status_code,
                            error_code=None,
                            rt_cd="ERROR",
                            msg_cd="NETWORK_ERROR",
                            msg1=f"주식일별 주문 체결 조회 실패: {e}",
                            payload={
                                "stage": "daily_order_execution",
                                "error": str(e),
                            }
                        )
                
                if attempt == HTTP_RETRY_COUNT - 1:
                    raise KISOrderError(
                        message=f"주식일별 주문 체결 조회 실패: {e}",
                        status_code=500,
                        error_code=None,
                        rt_cd="ERROR",
                        msg_cd="NETWORK_ERROR",
                        msg1=f"주식일별 주문 체결 조회 실패: {e}",
                        payload={
                            "stage": "daily_order_execution",
                            "error": str(e),
                        }
                    )
                await asyncio.sleep(0.5 * (attempt + 1))