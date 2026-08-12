from uuid import UUID
import uuid
from sqlalchemy import Uuid, DateTime

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot_type: Mapped[str]
    
    account_no: Mapped[str]
    account_product_code: Mapped[str]
    net_deposit: Mapped[int | None]
    
    rebalance_id: Mapped[uuid.UUID | None]
    cash_amount: Mapped[int | None]
    trading_date: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioSnapshotHolding(Base):
    __tablename__ = "portfolio_snapshot_holdings"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    stock_code: Mapped[str]
    stock_name: Mapped[str]
    holding_qty: Mapped[int]
    avg_buy_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())