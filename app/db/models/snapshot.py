from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[str] = mapped_column(primary_key=True)
    snapshot_at: Mapped[datetime]
    snapshot_type: Mapped[str]
    rebalance_id: Mapped[str | None]
    cash_amount: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PortfolioSnapshotHolding(Base):
    __tablename__ = "portfolio_snapshot_holdings"

    id: Mapped[str] = mapped_column(primary_key=True)
    snapshot_id: Mapped[str]
    stock_code: Mapped[str]
    stock_name: Mapped[str]
    holding_qty: Mapped[int]
    avg_buy_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())