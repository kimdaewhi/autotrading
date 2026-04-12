from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Rebalance(Base):
    __tablename__ = "rebalances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── 전략 정보 ──
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    screener_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── 파이프라인 결과 요약 ──
    universe_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    buy_signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sell_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    buy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    hold_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # ── 금액 요약 ──
    total_sell_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0, server_default="0")
    total_buy_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0, server_default="0")
    available_cash_before: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    estimated_cash_after: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # ── 실행 정보 ──
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", server_default="PENDING")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 전략 파라미터 / diff 스냅샷 ──
    strategy_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    diff_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── 시간 ──
    executed_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    completed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )