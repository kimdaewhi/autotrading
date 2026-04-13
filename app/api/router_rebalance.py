from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.kis.kis_account import KISAccount
from app.core.settings import settings
from app.db.session import get_db
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.services.kis.account_service import AccountService
from app.strategy.live.rebalance_service import RebalanceService
from app.strategy.screener.fscore import FScore
from app.strategy.strategies.momentum import MomentumStrategy
from app.strategy.universe.universe_filters import marcap_range

router = APIRouter()


@router.post("/run")
async def run_rebalance(
    year: int = 2024,
    dry_run: bool = True,
    db: AsyncSession = Depends(get_db),
):
    service = RebalanceService(
        screener=FScore(
            threshold=7, 
            universe_builder=lambda: marcap_range(min_cap=1e9, max_cap=1e12, n=150)
        ),
        strategy=MomentumStrategy(lookback_days=120, top_n=10),
        account_service=AccountService(
            kis_account=KISAccount(
                appkey=settings.KIS_APP_KEY,
                appsecret=settings.KIS_APP_SECRET,
                url=settings.kis_base_url,
            )
        ),
        data_provider=FDRMarketDataProvider(),
    )
    
    result = await service.run(year=year, dry_run=dry_run, db=db)
    
    return {
        "rebalance_id": result.rebalance_id,
        "success": result.success,
        "dry_run": result.dry_run,
        "error_message": result.error_message,
        "universe_count": result.universe_count,
        "signal_buy_count": result.signal_buy_count,
        "summary": result.summary(),
    }