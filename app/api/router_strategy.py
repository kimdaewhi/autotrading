# FastAPI
from fastapi import APIRouter, Depends, HTTPException, Query
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

# DB
from app.db.session import get_db

# Schemas
from app.schemas.rebalance.rebalance import RebalanceDetailResponse, RebalanceListResponse, RebalanceSnapshotResponse
from app.schemas.strategy.response import StrategyRunResponse
from app.schemas.strategy.trading import RebalanceResult

# Services
from app.services.rebalance.rebalance_query_service import RebalanceQueryService
from app.services.rebalance.rebalance_orchestrator import RebalanceOrchestrator

# Strategy
from app.strategy.runtime.executor_registry import get_executor
from app.strategy.screener.fscore import FScore
from app.strategy.signals.momentum import MomentumStrategy
from app.strategy.strategies.base_strategy import BaseStrategy
from app.strategy.strategies.piotroski_momentum_strategy import PiotroskiMomentumStrategy

# Data
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.universe.universe_filters import marcap_range

# Settings
from app.core.settings_strategy import strategy_settings


router = APIRouter()


# Dependency Injection을 위한 서비스 인스턴스 생성 함수
def get_rebalance_query_service() -> RebalanceQueryService:
    return RebalanceQueryService()


# 전략 팩토리 (FastAPI Dependency)
def get_default_strategy() -> BaseStrategy:
    """Piotroski + Momentum 전략 생성."""
    
    # TODO(P2/리밸런스): 향후 전략 추가 시, strategy_type 파라미터로 분기 처리하여 다양한 전략 생성 지원
    return PiotroskiMomentumStrategy(
        screener=FScore(
            threshold=strategy_settings.PM_FSCORE_THRESHOLD,
            universe_builder=lambda: marcap_range(
                min_cap=strategy_settings.PM_MIN_MARCAP,
                max_cap=strategy_settings.PM_MAX_MARCAP,
                n=strategy_settings.PM_UNIVERSE_N,
            ),
        ),
        momentum=MomentumStrategy(
            lookback_days=strategy_settings.PM_LOOKBACK_DAYS,
            top_n=strategy_settings.PM_TOP_N,
        ),
        data_provider=FDRMarketDataProvider(),
    )


@router.post("/run")
async def run_rebalance(
    year: int | None = None,
    dry_run: bool = True,
    db: AsyncSession = Depends(get_db),
    strategy: BaseStrategy = Depends(get_default_strategy),
):
    orchestrator = RebalanceOrchestrator(strategy)
    result = await orchestrator.run(db=db, year=year, dry_run=dry_run)
    
    return StrategyRunResponse(
        strategy_name=result.strategy_result.strategy_name,
        strategy_type=result.strategy_result.strategy_type.value,
        success=result.rebalance_result.success,
        dry_run=result.rebalance_result.dry_run,
        error_message=result.rebalance_result.error_message,
        summary=result.rebalance_result.summary(),
        metadata={
            "rebalance_id": result.rebalance_result.rebalance_id,
            "universe_count": result.rebalance_result.universe_count,
            "signal_buy_count": result.rebalance_result.signal_buy_count,
        },
    )


# ⚙️ 리밸런스 이력 조회 API - 과거 리밸런스 실행 결과 목록 조회 (페이징 지원)
@router.get("/rebalance/history", response_model=RebalanceListResponse, description="리밸런스 이력 목록 조회")
async def get_rebalance_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    service: RebalanceQueryService = Depends(get_rebalance_query_service),
) -> RebalanceListResponse:
    return await service.get_rebalance_list(db, limit=limit, offset=offset)



# ⚙️ 리밸런스 상세 조회 API - 리밸런스 실행 결과 및 시그널, 주문 내역 등 포함
@router.get("/rebalance/history/{rebalance_id}", response_model=RebalanceDetailResponse, description="리밸런스 상세 조회")
async def get_rebalance_detail(
    rebalance_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: RebalanceQueryService = Depends(get_rebalance_query_service),
) -> RebalanceDetailResponse:
    result = await service.get_rebalance_detail(db, rebalance_id)
    if result is None:
        raise HTTPException(status_code=404, detail="리밸런스를 찾을 수 없습니다.")
    return result


@router.get(
    "/rebalance/history/{rebalance_id}/snapshot",
    response_model=RebalanceSnapshotResponse,
    description="리밸런스 시점 포트폴리오 스냅샷 조회",
)
async def get_rebalance_snapshot(
    rebalance_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: RebalanceQueryService = Depends(get_rebalance_query_service),
) -> RebalanceSnapshotResponse:
    result = await service.get_rebalance_snapshot(db, rebalance_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="해당 리밸런스의 스냅샷을 찾을 수 없습니다.",
        )
    return result