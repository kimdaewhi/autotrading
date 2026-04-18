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



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Strategy Contract (전략 ↔ Executor 계약)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StrategyType(str, Enum):
    """전략 실행 유형 — Executor 라우팅에 사용"""
    REBALANCE = "REBALANCE"          # 포트폴리오 리밸런싱 (diff 계산 → 매도/매수)
    DIRECT_TRADE = "DIRECT_TRADE"    # 단일 종목 즉시 매매 (향후)


class TradeSide(str, Enum):
    """매매 방향"""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class TradeIntent:
    """
    전략이 "이 종목을 사고/팔고 싶다"는 의도 표현.
    
    Executor가 이걸 받아서 실제 수량 계산, 주문 생성을 처리한다.
    전략은 weight 또는 quantity 중 하나만 채우면 된다.
    """
    stock_code: str
    stock_name: str
    side: TradeSide
    
    # 비중 기반 (포트폴리오 전략) — Executor가 수량으로 변환
    # 예를들어, 포트폴리오 전략에서는 "이 종목에 전체 자산의 10%를 투자하고 싶다(weight)"는 식으로 비중을 반환
    # 혹은 단발성 매매 전략에서는 "이 종목을 100주 사겠다(quantity)"는 식으로 표현
    weight: float | None = None
    
    # 수량 직접 지정 (단일 매매 전략)
    quantity: int | None = None
    
    # 매매 가격 힌트 (시장가면 None)
    price_hint: int | None = None
    
    # 전략별 부가 정보
    reason: str = ""
    
    # 전략별로 부가 정보가 다르므로 자유롭게 담을 수 있는 딕셔너리 (로깅, 디버깅용)
    metadata: dict = field(default_factory=dict)


@dataclass
class StrategyResult:
    """
    전략의 execute() 반환값.
    
    어떤 전략이든 이 형태로 반환하면 Executor가 처리할 수 있다.
    """
    strategy_type: StrategyType
    strategy_name: str
    orders: list[TradeIntent] = field(default_factory=list)
    
    # 전략 실행 과정의 부가 정보 (로깅, 디버깅용)
    metadata: dict = field(default_factory=dict)
    
    @property
    def buy_count(self) -> int:
        return sum(1 for o in self.orders if o.side == TradeSide.BUY)
    
    @property
    def sell_count(self) -> int:
        return sum(1 for o in self.orders if o.side == TradeSide.SELL)
    
    def summary(self) -> str:
        lines = [
            f"📋 전략 실행 결과: {self.strategy_name}",
            f"   유형: {self.strategy_type.value}",
            f"   BUY: {self.buy_count}건, SELL: {self.sell_count}건",
        ]
        for o in self.orders:
            detail = f"weight={o.weight:.1%}" if o.weight else f"qty={o.quantity}"
            lines.append(f"   {o.side.value} {o.stock_code} {o.stock_name} ({detail}) {o.reason}")
        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Exit Decision — 전략의 청산 판정 결과
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ExitReason(str, Enum):
    """
    청산 사유.
    
    전략마다 고유한 청산 조건이 있을 수 있으므로
    필요 시 여기에 값을 추가한다. (예: TRAILING_STOP, SIGNAL_REVERSE)
    """
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TIME_EXIT = "time_exit"


@dataclass
class ExitDecision:
    """
    전략의 청산 판정 결과.
    Executor는 이 객체를 받아 should_exit=True면 매도를 집행한다.
    reason은 SwingTradeRecord.exit_reason에 기록되어 분석에 사용된다.
    
    의사 결정 도메인이므로 trading.py에 위치시키고, 전략별로 확장 가능한 형태로 설계한다.
    """
    should_exit: bool
    reason: ExitReason | None = None
    exit_price_hint: float | None = None
    metadata: dict = field(default_factory=dict)