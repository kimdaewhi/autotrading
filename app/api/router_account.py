from fastapi import APIRouter, Depends

from app.broker.kis.kis_account import KISAccount
from app.core.settings import settings
from app.schemas.kis.kis import BalanceResponse
import app.schemas.kis.account as account_schemas
from app.services.kis.account_service import AccountService

router = APIRouter()


def get_kis_account() -> KISAccount:
    return KISAccount(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )


def get_account_service(kis_account: KISAccount = Depends(get_kis_account)) -> AccountService:
    return AccountService(kis_account=kis_account)



def get_kis_account() -> KISAccount:
    return KISAccount(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )


def get_account_service(
    kis_account: KISAccount = Depends(get_kis_account)
) -> AccountService:
    return AccountService(kis_account=kis_account)


# 계좌 잔고 원본 조회
@router.get("/balance", response_model=BalanceResponse, description="계좌 잔고 조회(브로커 응답 원본)")
async def get_account_balance(
    account_service: AccountService = Depends(get_account_service)
) -> BalanceResponse:
    return await account_service.get_account_balance()


# 보유 종목 목록 조회
@router.get("/holdings", response_model=list[account_schemas.HoldingRead], description="보유 종목 목록 조회")
async def get_holding_list(
    account_service: AccountService = Depends(get_account_service)
) -> list[account_schemas.HoldingRead]:
    return await account_service.get_holding_list()


# 계좌 요약 정보 조회
@router.get("/summary", response_model=account_schemas.AccountSummaryRead, description="계좌 요약 정보 조회")
async def get_account_summary(
    account_service: AccountService = Depends(get_account_service)
) -> account_schemas.AccountSummaryRead:
    return await account_service.get_account_summary()


# 대시보드 통합 조회
@router.get("/dashboard", response_model=account_schemas.AccountDashboardRead, description="대시보드 통합 조회 (balance 1회 호출)")
async def get_dashboard(
    account_service: AccountService = Depends(get_account_service)
) -> account_schemas.AccountDashboardRead:
    return await account_service.get_dashboard()