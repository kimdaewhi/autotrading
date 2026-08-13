from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repository.rebalance_repository import get_completed_rebalance_dates
from app.schemas.strategy import metrics as metrics_schemas
from app.services.metrics.performance_service import PerformanceService

router = APIRouter()


def get_performance_service() -> PerformanceService:
    return PerformanceService()


# 전략 성과 지표 조회
@router.get(
    "/performance",
    response_model=metrics_schemas.PerformanceRead,
    description="전략 성과 지표 조회 (수익률 / 리스크 / 거래 / 회전율)",
)
async def get_performance(
    start_date: date | None = Query(
        None, description="조회 시작일. 미지정 시 최초 리밸런싱 실행일부터 계산한다."
    ),
    as_of_date: date | None = Query(
        None, description="조회 종료일. 미지정 시 오늘."
    ),
    db: AsyncSession = Depends(get_db),
    performance_service: PerformanceService = Depends(get_performance_service),
) -> metrics_schemas.PerformanceRead:
    # 시작일 미지정 시 최초 리밸런싱 실행일을 기준으로 삼는다.
    # 리밸런싱 이력이 없으면 계산할 NAV 자체가 없으므로 빈 응답.
    if start_date is None:
        rebalance_dates = await get_completed_rebalance_dates(
            db=db, start_date=date.min, end_date=as_of_date or date.today()
        )
        if not rebalance_dates:
            return metrics_schemas.PerformanceRead.empty()
        start_date = min(rebalance_dates)

    return await performance_service.get_performance(
        db=db, start_date=start_date, as_of_date=as_of_date
    )