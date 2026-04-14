from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


# ── 리밸런스 목록 조회용 (간략) ──
class RebalanceListItem(BaseModel):
    id: UUID
    strategy_name: str
    screener_name: str | None
    status: str
    buy_signal_count: int
    buy_count: int
    sell_count: int
    executed_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class RebalanceListResponse(BaseModel):
    total_count: int
    items: list[RebalanceListItem]


# ── 리밸런스 상세 조회용 ──
class RebalanceOrderItem(BaseModel):
    id: UUID
    stock_code: str
    order_pos: str
    order_type: str
    order_qty: int
    filled_qty: int
    remaining_qty: int
    avg_fill_price: Decimal | None
    status: str
    submitted_at: datetime | None
    updated_at: datetime

    # 체결 소요시간 (초)
    fill_duration_seconds: float | None

    model_config = {"from_attributes": True}


class RebalanceExecutionSummary(BaseModel):
    """리밸런싱 실행 요약 (대시보드 상단 카드 4개)"""
    # 편입 실패율
    signal_count: int
    filled_count: int
    fail_rate: float

    # 예수금 비율
    available_cash_before: Decimal | None
    estimated_cash_after: Decimal | None
    cash_ratio: float | None

    # 리밸런싱 소요시간 (초)
    rebalance_duration_seconds: float | None

    # 평균 체결 소요시간 (초)
    avg_fill_duration_seconds: float | None


class RebalanceDetailResponse(BaseModel):
    """리밸런스 상세 조회 응답"""
    # 리밸런스 기본 정보
    id: UUID
    strategy_name: str
    screener_name: str | None
    status: str
    universe_count: int
    buy_signal_count: int
    buy_count: int
    sell_count: int
    hold_count: int
    total_sell_value: Decimal
    total_buy_value: Decimal
    available_cash_before: Decimal | None
    estimated_cash_after: Decimal | None
    dry_run: bool
    strategy_params: dict | None
    executed_at: datetime
    completed_at: datetime | None

    # 가공된 실행 요약
    execution_summary: RebalanceExecutionSummary

    # 주문 내역
    orders: list[RebalanceOrderItem]