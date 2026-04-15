"""
⭐ 리밸런싱 관련 스키마 (Dataclass / Enum)

position_diff, order_generator, rebalance_service에서 사용하는
데이터 클래스를 한 곳에 모아 순환 참조를 방지한다.

포함:
    - DiffAction, PositionDiffItem, PositionDiffResult, CurrentHolding
    - OrderRequest, FillResult, OrderGenerationResult
    - RebalanceResult
"""

import math
from dataclasses import dataclass, field
from enum import Enum


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Position Diff
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DiffAction(str, Enum):
    """포지션 변경 액션"""
    SELL = "SELL"
    BUY = "BUY"
    HOLD = "HOLD"
    REBALANCE = "REBALANCE"


@dataclass
class PositionDiffItem:
    """개별 종목의 포지션 변경 정보"""
    stock_code: str
    stock_name: str
    action: DiffAction
    
    # 현재 보유 정보
    current_qty: int = 0
    current_price: int = 0
    current_value: int = 0
    
    # 목표 정보
    target_qty: int = 0
    target_value: int = 0
    
    # 주문 정보 (계산 결과)
    order_qty: int = 0
    order_value: int = 0
    
    # 모멘텀 부가 정보
    momentum_return: float = 0.0
    momentum_rank: int = 0


@dataclass
class PositionDiffResult:
    """포지션 diff 계산 결과 전체"""
    sell_list: list[PositionDiffItem] = field(default_factory=list)
    buy_list: list[PositionDiffItem] = field(default_factory=list)
    hold_list: list[PositionDiffItem] = field(default_factory=list)
    
    # 요약 정보
    total_sell_value: int = 0
    total_buy_value: int = 0
    available_cash: int = 0
    estimated_cash_after: int = 0
    
    # 유니버스 정보
    target_count: int = 0
    current_count: int = 0
    
    def summary(self) -> str:
        """리밸런싱 계획 요약 문자열"""
        lines = [
            "=" * 60,
            "📊 리밸런싱 계획 요약",
            "=" * 60,
            f"☑️ 현재 보유: {self.current_count}종목 / 목표: {self.target_count}종목",
            f"💸 예수금: {self.available_cash:,.0f}원",
            "",
            f"🔴 매도 ({len(self.sell_list)}종목): {self.total_sell_value:,.0f}원",
        ]
        for item in self.sell_list:
            lines.append(
                f"   {item.stock_code} {item.stock_name}: "
                f"{item.order_qty}주 × {item.current_price:,}원 = {item.order_value:,.0f}원"
            )
        
        lines.append(f"\n🟢 매수 ({len(self.buy_list)}종목): {self.total_buy_value:,.0f}원")
        for item in self.buy_list:
            lines.append(
                f"   {item.stock_code} {item.stock_name}: "
                f"{item.order_qty}주 × {item.current_price:,}원 = {item.order_value:,.0f}원"
                f" (수익률: {item.momentum_return:.1%}, 순위: {item.momentum_rank})"
            )
        
        lines.append(f"\n⚪ 유지 ({len(self.hold_list)}종목)")
        for item in self.hold_list:
            lines.append(
                f"   {item.stock_code} {item.stock_name}: "
                f"{item.current_qty}주 (평가: {item.current_value:,.0f}원)"
            )
        
        lines.append(f"\n💰 리밸런싱 후 예상 잔여 현금: {self.estimated_cash_after:,.0f}원")
        lines.append("=" * 60)
        
        return "\n".join(lines)


@dataclass
class CurrentHolding:
    """현재 보유 종목 정보 (AccountService 응답을 정규화한 구조체)"""
    stock_code: str
    stock_name: str
    quantity: int
    current_price: int
    eval_amount: int


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Order Generator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class OrderRequest:
    """worker-1에 전달할 주문 요청 정보"""
    order_id: str
    stock_code: str
    stock_name: str
    action: str
    quantity: int
    price: int
    order_type: str
    order_kind: str
    
    # 추적용
    rebalance_id: str = ""
    diff_action: str = ""


@dataclass
class FillResult:
    """체결 대기 결과"""
    total_orders: int = 0
    filled_orders: int = 0
    canceled_orders: int = 0
    failed_orders: int = 0
    total_filled_amount: int = 0
    timed_out: bool = False
    canceled_by_timeout: int = 0


@dataclass
class OrderGenerationResult:
    """주문 생성 결과"""
    rebalance_id: str = ""
    sell_orders: list[OrderRequest] = field(default_factory=list)
    buy_orders: list[OrderRequest] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    
    # 체결 대기 결과
    sell_fill_result: FillResult | None = None
    buy_fill_result: FillResult | None = None
    
    @property
    def total_orders(self) -> int:
        return len(self.sell_orders) + len(self.buy_orders)
    
    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"📋 주문 생성 결과 (rebalance_id: {self.rebalance_id})",
            "=" * 60,
            f"매도 주문: {len(self.sell_orders)}건",
        ]
        for o in self.sell_orders:
            lines.append(f"   [{o.order_id[:8]}] {o.stock_code} {o.stock_name}: {o.quantity}주 매도")
        
        if self.sell_fill_result:
            sfr = self.sell_fill_result
            lines.append(
                f"   → 체결: {sfr.filled_orders}/{sfr.total_orders}건, "
                f"체결금액: {sfr.total_filled_amount:,}원"
                f"{' (타임아웃)' if sfr.timed_out else ''}"
            )
        
        lines.append(f"매수 주문: {len(self.buy_orders)}건")
        for o in self.buy_orders:
            lines.append(f"   [{o.order_id[:8]}] {o.stock_code} {o.stock_name}: {o.quantity}주 매수")
        
        if self.buy_fill_result:
            bfr = self.buy_fill_result
            lines.append(
                f"   → 체결: {bfr.filled_orders}/{bfr.total_orders}건"
                f"{' (타임아웃)' if bfr.timed_out else ''}"
            )
        
        if self.skipped:
            lines.append(f"건너뜀: {len(self.skipped)}건")
            for s in self.skipped:
                lines.append(f"   {s['stock_code']}: {s['reason']}")
        
        lines.append("=" * 60)
        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Rebalance Result
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class RebalanceResult:
    """리밸런싱 실행 결과"""
    rebalance_id: str = ""
    executed_at: str = ""
    
    # 파이프라인 단계별 결과
    universe_count: int = 0
    signal_buy_count: int = 0
    diff_result: PositionDiffResult | None = None
    order_result: OrderGenerationResult | None = None
    
    # 상태
    dry_run: bool = True
    success: bool = False
    error_message: str = ""
    
    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"🚀 리밸런싱 실행 결과",
            f"   실행 시각: {self.executed_at}",
            f"   rebalance_id: {self.rebalance_id}",
            f"   모드: {'DRY RUN (검증만)' if self.dry_run else '실전 주문'}",
            "=" * 60,
            f"📌 유니버스: {self.universe_count}종목 통과",
            f"📌 BUY 시그널: {self.signal_buy_count}종목",
        ]
        
        if self.diff_result:
            lines.append("")
            lines.append(self.diff_result.summary())
        
        if self.order_result:
            lines.append("")
            lines.append(self.order_result.summary())
        
        if self.error_message:
            lines.append(f"\n❌ 오류: {self.error_message}")
        
        return "\n".join(lines)