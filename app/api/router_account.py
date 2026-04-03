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



# 계좌 잔고 조회
@router.get("/balance", response_model=BalanceResponse)
async def get_account_balance(
    account_service: AccountService = Depends(get_account_service)
) -> BalanceResponse:
    balance = await account_service.get_account_balance()
    return balance


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


# 수익 / 손실 종목 분리 조회
@router.get("/profit-loss", response_model=dict[str, list[account_schemas.HoldingRead]], description="수익 / 손실 종목 분리 조회")
async def get_profit_loss_holdings(
    account_service: AccountService = Depends(get_account_service)
) -> dict[str, list[account_schemas.HoldingRead]]:
    profit_holdings, loss_holdings = await account_service.get_profit_loss_holdings()
    return {
        "profit_holdings": profit_holdings,
        "loss_holdings": loss_holdings,
    }


# 매도 가능 종목 목록 조회
@router.get("/sellable", response_model=list[account_schemas.HoldingRead], description="매도 가능 종목 목록 조회")
async def get_sellable_holdings(
    account_service: AccountService = Depends(get_account_service)
) -> list[account_schemas.HoldingRead]:
    return await account_service.get_sellable_holdings()


# 당일 매매 현황 조회
@router.get("/today", response_model=account_schemas.TodayTradingSummaryRead, description="당일 매매 현황 조회")
async def get_today_trading_summary(
    account_service: AccountService = Depends(get_account_service)
) -> account_schemas.TodayTradingSummaryRead:
    return await account_service.get_today_trading_summary()


# 보유 종목 통계 조회
@router.get("/stats", response_model=account_schemas.HoldingStatsRead, description="보유 종목 통계 조회")
async def get_holding_stats(
    account_service: AccountService = Depends(get_account_service)
) -> account_schemas.HoldingStatsRead:
    return await account_service.get_holding_stats()


# 최고 수익 / 최고 손실 종목 조회
@router.get("/top", response_model=account_schemas.TopHoldingPairRead, description="최고 수익 / 최고 손실 종목 조회")
async def get_top_profit_loss_holdings(
    account_service: AccountService = Depends(get_account_service)
) -> account_schemas.TopHoldingPairRead:
    return await account_service.get_top_profit_loss_holdings()