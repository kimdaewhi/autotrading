import httpx
from app.schemas.kis import BalanceResponse
from app.utils.logger import get_logger
from app.core.exceptions import KisAuthError
from app.core.settings import settings

logger = get_logger(__name__)

class KISAccount:
    def __init__(self, appkey: str, appsecret: str, url: str = f"{settings.kis_base_url}/uapi/domestic-stock/v1/trading/inquire-balance") -> None:
        self.appkey = appkey
        self.appsecret = appsecret
        self.url = url