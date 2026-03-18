import httpx
from app.schemas.kis import BalanceResponse
from app.utils.logger import get_logger
from app.broker.kis.base import KISBase
from app.core.exceptions import KisAuthError
from app.core.settings import settings

logger = get_logger(__name__)

class KISAccount(KISBase):
    def __init__(self, appkey: str, appsecret: str, url: str = settings.kis_base_url) -> None:
        super().__init__(appkey, appsecret, url)
    
    
    # ⚙️ KIS API로부터 계좌 잔고 조회
    def get_balance(self, access_token: str, account_no: str, account_product_code: str, endpoint: str = "/uapi/domestic-stock/v1/trading/inquire-balance") -> BalanceResponse:
        url = f"{self.url}{endpoint}"
        
        headers = self.build_headers(
            access_token=access_token,
            tr_id="VTTC8434R" if settings.TRADING_ENV == "paper" else "TTTC8434R"
        )
        
        params = {
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
        
        logger.info(f"계좌 잔고 조회 요청 : {self.url}{endpoint}")
        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") != "0":
                raise KisAuthError(f"KIS API Error: {data.get('msg1')}")
            return BalanceResponse(**data)
        except httpx.HTTPError as e:
            logger.error(f"계좌 잔고 조회 실패: {e}")
            raise KisAuthError("계좌 잔고 조회 중 오류가 발생했습니다.")