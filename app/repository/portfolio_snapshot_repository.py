from __future__ import annotations
from datetime import date

from sqlalchemy import Sequence, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.snapshot import PortfolioSnapshot, PortfolioSnapshotHolding
from app.schemas.strategy.trading import StrategyType


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


# ⚙️ 계좌별 기간 내 스냅샷 조회
async def get_snapshots_by_period(
    db: AsyncSession,
    account_no: str,
    account_product_code: str,
    start_date: date, 
    end_date: date
) -> Sequence[PortfolioSnapshot]:
    stmt = (
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.account_no == account_no,
            PortfolioSnapshot.account_product_code == account_product_code,
            PortfolioSnapshot.snapshot_type == StrategyType.REBALANCE.value,
            PortfolioSnapshot.trading_date >= start_date,
            PortfolioSnapshot.trading_date <= end_date,
        )
        .order_by(PortfolioSnapshot.trading_date.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ⚙️ 여러 스냅샷의 보유 종목 일괄 조회
async def get_holdings_by_snapshot_ids(
    db: AsyncSession,
    snapshot_ids: list[str],
) -> Sequence[PortfolioSnapshotHolding]:
    stmt = (
        select(PortfolioSnapshotHolding)
        .where(PortfolioSnapshotHolding.snapshot_id.in_(snapshot_ids))
        .order_by(PortfolioSnapshotHolding.snapshot_id, PortfolioSnapshotHolding.stock_code)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


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



# ⚙️ rebalance_id로 스냅샷 메타 조회
async def get_snapshot_by_rebalance(
    db: AsyncSession,
    rebalance_id: str,
) -> PortfolioSnapshot | None:
    stmt = select(PortfolioSnapshot).where(
        PortfolioSnapshot.rebalance_id == rebalance_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ⚙️ snapshot_id로 보유 종목 목록 조회
async def get_snapshot_holdings(
    db: AsyncSession,
    snapshot_id: str,
) -> Sequence[PortfolioSnapshotHolding]:
    stmt = (
        select(PortfolioSnapshotHolding)
        .where(PortfolioSnapshotHolding.snapshot_id == snapshot_id)
        .order_by(PortfolioSnapshotHolding.stock_code)
    )
    result = await db.execute(stmt)
    return result.scalars().all()