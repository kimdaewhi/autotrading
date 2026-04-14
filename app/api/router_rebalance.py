from http.client import HTTPException
from fastapi import APIRouter, Depends, Query
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.kis.kis_account import KISAccount
from app.core.settings import settings
from app.db.session import get_db
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.schemas.rebalance.rebalance import RebalanceDetailResponse, RebalanceListResponse
from app.services.kis.account_service import AccountService
from app.services.rebalance.rebalance_query_service import RebalanceQueryService
from app.strategy.live.rebalance_service import RebalanceService
from app.strategy.screener.fscore import FScore
from app.strategy.strategies.momentum import MomentumStrategy
from app.strategy.universe.universe_filters import marcap_range

router = APIRouter()

# Dependency Injection을 위한 서비스 인스턴스 생성 함수
def get_rebalance_query_service() -> RebalanceQueryService:
    return RebalanceQueryService()


# ⚙️ 리밸런스 실행 API - 전략에 따라 리밸런스 실행 (dry run 옵션으로 실제 주문 실행 여부 결정)
@router.post("/run")
async def run_rebalance(
    year: int = 2024,
    dry_run: bool = True,
    db: AsyncSession = Depends(get_db),
):
    min_marcap = 1e12   # 1조
    max_marcap = 10e12   # 5조
    
    # TODO(P2/전략) : 파라미터 조정 필수
    service = RebalanceService(
        screener=FScore(
            threshold=7, 
            universe_builder=lambda: marcap_range(min_cap=min_marcap, max_cap=max_marcap, n=150)
        ),
        strategy=MomentumStrategy(lookback_days=300, top_n=25),
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


# ⚙️ 리밸런스 이력 조회 API - 과거 리밸런스 실행 결과 목록 조회 (페이징 지원)
@router.get("/history", response_model=RebalanceListResponse, description="리밸런스 이력 목록 조회")
async def get_rebalance_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    service: RebalanceQueryService = Depends(get_rebalance_query_service),
) -> RebalanceListResponse:
    return await service.get_rebalance_list(db, limit=limit, offset=offset)


# ⚙️ 리밸런스 상세 조회 API - 리밸런스 실행 결과 및 시그널, 주문 내역 등 포함
@router.get("/history/{rebalance_id}", response_model=RebalanceDetailResponse, description="리밸런스 상세 조회")
async def get_rebalance_detail(
    rebalance_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: RebalanceQueryService = Depends(get_rebalance_query_service),
) -> RebalanceDetailResponse:
    result = await service.get_rebalance_detail(db, rebalance_id)
    if result is None:
        raise HTTPException(status_code=404, detail="리밸런스를 찾을 수 없습니다.")
    return result