from fastapi import APIRouter, Depends

from app.broker.kis.kis_account import KISAccount
from app.schemas.kis import BalanceResponse
from app.core.settings import settings
from app.services.account_service import AccountService

router = APIRouter()


def get_kis_account() -> KISAccount:
    return KISAccount(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )


def get_account_service(kis_account: KISAccount = Depends(get_kis_account)) -> AccountService:
    return AccountService(kis_account=kis_account)



# 계좌 잔고 조회
@router.get("/balance", response_model=BalanceResponse)
async def get_account_balance(
    account_service: AccountService = Depends(get_account_service)
) -> BalanceResponse:
    balance = await account_service.get_account_balance()
    return balance