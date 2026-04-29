"""리밸런싱 관련 DB 조회 리포지토리.

라우터/서비스용 조회 함수와 자동 리밸런싱 워커용 게이트 함수를 함께 둔다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import REBALANCE_STATUS
from app.db.models.rebalance import Rebalance

KST = ZoneInfo("Asia/Seoul")


# ─────────────────────────────────────────────────────────────
# 조회용 (라우터/서비스에서 사용)
# ─────────────────────────────────────────────────────────────

# ⚙️ 리밸런스 이력 목록 조회 (최신순)
async def get_rebalances(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> Sequence[Rebalance]:
    stmt = (
        select(Rebalance)
        .order_by(Rebalance.executed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ⚙️ 리밸런스 단건 조회
async def get_rebalance_by_id(
    db: AsyncSession,
    rebalance_id: UUID,
) -> Rebalance | None:
    stmt = select(Rebalance).where(Rebalance.id == rebalance_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ⚙️ 리밸런스 총 개수 조회 (페이징용)
async def get_rebalance_count(db: AsyncSession) -> int:
    stmt = select(func.count()).select_from(Rebalance)
    result = await db.execute(stmt)
    return result.scalar_one()


# ─────────────────────────────────────────────────────────────
# 자동 리밸런싱 워커용 (tasks_rebalance.py에서 사용)
# ─────────────────────────────────────────────────────────────

# ⚙️ 직전 성공 리밸런싱 일자 조회 (RebalanceWindow 주입용)
async def get_last_completed_rebalance_date(db: AsyncSession) -> date | None:
    """직전에 성공적으로 완료된 리밸런싱의 실행 일자(KST)를 반환.
    
    Returns:
        - 가장 최근 COMPLETED + dry_run=False 리밸런싱의 executed_at 날짜 (KST)
        - 없으면 None (첫 자동 리밸런싱 시점 — 자동 진행 차단 정책용)
    """
    stmt = (
        select(Rebalance.executed_at)
        .where(
            Rebalance.status == REBALANCE_STATUS.COMPLETED,
            Rebalance.dry_run == False,  # noqa: E712
        )
        .order_by(Rebalance.executed_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    last_executed_at: datetime | None = result.scalar_one_or_none()
    
    if last_executed_at is None:
        return None
    
    # tz-aware → KST 날짜로 변환
    return last_executed_at.astimezone(KST).date()


# ⚙️ 같은 달 중복 실행 체크 (idempotency)
async def has_completed_rebalance_in_month(
    db: AsyncSession,
    target_month: date,
) -> bool:
    """target_month(년-월)에 이미 실행 중이거나 완료된 리밸런싱이 있는지 확인.
    
    같은 달 중복 실행 차단용. RUNNING 또는 COMPLETED 상태인 row가 있으면 True.
    
    Args:
        target_month: 체크할 달 (day는 무시되고 year-month만 사용됨)
    
    Returns:
        True면 이미 실행됐거나 진행 중 → 스킵해야 함
        False면 이번 달엔 아직 안 돌았음 → 실행 가능
    """
    month_start = date(target_month.year, target_month.month, 1)
    
    stmt = (
        select(Rebalance.id)
        .where(
            Rebalance.status.in_([
                REBALANCE_STATUS.RUNNING,
                REBALANCE_STATUS.COMPLETED,
            ]),
            Rebalance.dry_run == False,  # noqa: E712
            func.date_trunc('month', Rebalance.executed_at) == month_start,
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None