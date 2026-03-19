from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models.order_event import OrderEvent


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    account_no: Mapped[str] = mapped_column(String(8), nullable=False)
    account_product_code: Mapped[str] = mapped_column(String(2), nullable=False)

    market: Mapped[str] = mapped_column(String(16), nullable=False, default="KRX", server_default="KRX")
    stock_code: Mapped[str] = mapped_column(String(12), nullable=False)

    order_pos: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    order_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    order_qty: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(24), nullable=False)

    requested_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    submitted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    broker_order_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    broker_org_no: Mapped[str | None] = mapped_column(String(16), nullable=True)

    rt_cd: Mapped[str | None] = mapped_column(String(8), nullable=True)
    msg_cd: Mapped[str | None] = mapped_column(String(32), nullable=True)
    msg1: Mapped[str | None] = mapped_column(Text, nullable=True)

    filled_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    request_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submit_response_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    events: Mapped[list["OrderEvent"]] = relationship(
        "OrderEvent",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )