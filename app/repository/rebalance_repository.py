from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import Sequence

from app.db.models.rebalance import Rebalance


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