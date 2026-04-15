import asyncio
import httpx
from app.core.constants import HTTP_RETRY_COUNT
from app.schemas.kis.kis import BalanceResponse
from app.utils.logger import get_logger
from app.broker.kis.base import KISBase
import app.broker.kis.enums as kis_enums
from app.core.exceptions import KISAccountError
from app.core.settings import settings

logger = get_logger(__name__)

class KISAccount(KISBase):
    def __init__(self, appkey: str, appsecret: str, url: str = settings.kis_base_url) -> None:
        super().__init__(appkey, appsecret, url)
    
    
    # ⚙️ KIS API로부터 계좌 잔고 조회
    async def get_balance(
        self,
        access_token: str,
        account_no: str,
        account_product_code: str,
        endpoint: str = "/uapi/domestic-stock/v1/trading/inquire-balance",
    ) -> BalanceResponse:
        url = f"{self.url}{endpoint}"
        tr_id = kis_enums.TRID.DOMESTIC_STOCK_BALANCE.resolve(
            settings.TRADING_ENV == "paper"
        )
        
        headers = self.build_headers(
            access_token=access_token,
            tr_id=tr_id,
        )
        
        base_params = {
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        
        logger.info(f"계좌 잔고 조회 요청 : {url} | tr_id : {tr_id} | account_no : {account_no}")
        
        all_output1 = []
        ctx_fk100 = ""
        ctx_nk100 = ""
        final_data = None
        
        while True:
            params = {**base_params, "CTX_AREA_FK100": ctx_fk100, "CTX_AREA_NK100": ctx_nk100}
            
            for attempt in range(HTTP_RETRY_COUNT):
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(url, headers=headers, params=params)
                    
                    if 500 <= resp.status_code < 600:
                        raise httpx.HTTPStatusError(
                            f"서버 오류: {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    
                    resp.raise_for_status()
                    data = resp.json()
                    break
                
                except (httpx.RequestError, httpx.TimeoutException) as e:
                    if attempt == HTTP_RETRY_COUNT - 1:
                        raise KISAccountError(
                            message=f"계좌 잔고 조회 요청 실패: {e}",
                            status_code=500,
                            error_code="NETWORK_ERROR",
                            rt_cd="ERROR",
                            msg_cd="NETWORK_ERROR",
                            msg1=f"계좌 잔고 조회 요청 실패: {e}",
                            payload={"stage": "get_balance", "error": str(e)},
                        )
                    await asyncio.sleep(0.5 * (attempt + 1))
                
                except httpx.HTTPStatusError as e:
                    error_payload = None
                    msg1 = f"계좌 잔고 조회 실패: HTTP {e.response.status_code}"
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
                        raise KISAccountError(
                            message=msg1,
                            status_code=e.response.status_code,
                            error_code=msg_cd,
                            rt_cd=rt_cd,
                            msg_cd=msg_cd,
                            msg1=msg1,
                            payload={"stage": "get_balance", "status_code": e.response.status_code, "response": error_payload},
                        )
                    await asyncio.sleep(0.5 * (attempt + 1))
            
            if data.get("rt_cd") != "0":
                raise KISAccountError(
                    message=data.get("msg1", "계좌 잔고 조회 실패"),
                    status_code=400,
                    error_code=data.get("msg_cd"),
                    rt_cd=data.get("rt_cd"),
                    msg_cd=data.get("msg_cd"),
                    msg1=data.get("msg1"),
                    payload=data,
                )
            
            # output1 누적
            all_output1.extend(data.get("output1", []))
            final_data = data
            
            # 연속조회 키 확인
            next_fk100 = data.get("ctx_area_fk100", "").strip()
            next_nk100 = data.get("ctx_area_nk100", "").strip()
            
            if not next_fk100 and not next_nk100:
                break
            if next_fk100 == ctx_fk100 and next_nk100 == ctx_nk100:
                break  # 무한루프 방지
            
            ctx_fk100 = next_fk100
            ctx_nk100 = next_nk100
            
            logger.info(f"계좌 잔고 조회 요청 : {url} | tr_id : {tr_id} | account_no : {account_no}")
        
        # 최종 응답에 누적된 output1 합치기
        final_data["output1"] = all_output1
        
        logger.info(f"계좌 잔고 조회 성공")
        return BalanceResponse(**final_data)