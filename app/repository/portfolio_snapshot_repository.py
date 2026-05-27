from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.snapshot import PortfolioSnapshot, PortfolioSnapshotHolding


# ─────────────────────────────────────────────────────────────
# 조회용
# ─────────────────────────────────────────────────────────────

# ⚙️ rebalance_id로 기존 스냅샷 존재 여부 조회 (멱등성 체크용)
async def get_snapshot_id_by_rebalance(
    db: AsyncSession,
    rebalance_id: str,
) -> str | None:
    stmt = select(PortfolioSnapshot.id).where(
        PortfolioSnapshot.rebalance_id == rebalance_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ─────────────────────────────────────────────────────────────
# 저장용
# ─────────────────────────────────────────────────────────────

# ⚙️ 포트폴리오 스냅샷 저장 (메타 + holdings)
async def insert_snapshot(
    db: AsyncSession,
    snapshot: PortfolioSnapshot,
    holdings: list[PortfolioSnapshotHolding],
) -> None:
    db.add(snapshot)
    db.add_all(holdings)
    await db.flush()