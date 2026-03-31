from app.broker.kis.kis_account import KISAccount
from app.core.settings import settings
from app.schemas.kis import BalanceResponse


class AccountService:
    """ 
    _summary_
    계좌 서비스 클래스
    
    _description_
    계좌 관련 기능을 제공하는 서비스 클래스입니다.
    """
    def __init__(self, kis_account: KISAccount):
        self.kis_account = kis_account
    
    
    
    # ⚙️ 계좌 잔고 조회
    async def get_account_balance(self, access_token: str) -> BalanceResponse:
        balance = await self.kis_account.get_balance(
            access_token=access_token,
            account_no=settings.KIS_ACCOUNT_NO,
            account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        )
        return balance