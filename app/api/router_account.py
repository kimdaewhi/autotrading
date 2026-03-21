from fastapi import APIRouter, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.broker.kis.kis_account import KISAccount
from app.schemas.kis import BalanceResponse
from app.core.settings import settings

security = HTTPBearer()
router = APIRouter()

def get_kis_account() -> KISAccount:
    return KISAccount(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )

# 계좌 잔고 조회
@router.get("/balance", response_model=BalanceResponse)
async def get_account_balance(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    kis_account: KISAccount = Depends(get_kis_account),
) -> BalanceResponse:
    access_token = credentials.credentials

    balance = await kis_account.get_balance(
        access_token=access_token,
        account_no=settings.KIS_ACCOUNT_NO,
        account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
    )
    return balance