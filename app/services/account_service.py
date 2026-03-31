import redis.asyncio as redis
from app.broker.kis.kis_account import KISAccount
from app.broker.kis.kis_auth import KISAuth
from app.core.settings import settings
from app.schemas.kis import BalanceResponse
from app.services.auth_service import AuthService


class AccountService:
    """ 
    _summary_
    계좌 서비스 클래스
    
    _description_
    계좌 관련 기능을 제공하는 서비스 클래스입니다.
    """
    def __init__(self, kis_account: KISAccount) -> None:
        self.kis_account = kis_account
    
    
    
    # ⚙️ 계좌 잔고 조회
    async def get_account_balance(self) -> BalanceResponse:
        # 1. Redis 클라이언트 생성 및 access token 발급(or 사용)
        redis_client = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
        auth_service = AuthService(
            auth_broker=KISAuth(
                appkey=settings.KIS_APP_KEY,
                appsecret=settings.KIS_APP_SECRET,
                url=f"{settings.kis_base_url}",
            ),
            redis_client=redis_client,
        )
        access_token = await auth_service.get_valid_access_token()
        
        # 2. KISAccount broker 통해 계좌 잔고 조회
        balance = await self.kis_account.get_balance(
            access_token=access_token,
            account_no=settings.KIS_ACCOUNT_NO,
            account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        )
        return balance