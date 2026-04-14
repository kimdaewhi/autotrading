from datetime import timedelta
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.rebalance import Rebalance
from app.db.models.order import Order
from app.repository.rebalance_repository import (
    get_rebalances,
    get_rebalance_by_id,
    get_rebalance_count,
)
from app.repository.order_repository import get_orders_by_rebalance_id
from app.schemas.rebalance.rebalance import (
    RebalanceListItem,
    RebalanceListResponse,
    RebalanceOrderItem,
    RebalanceExecutionSummary,
    RebalanceDetailResponse,
)


class RebalanceQueryService:

    # ⚙️ 리밸런스 이력 목록 조회
    async def get_rebalance_list(
        self,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
    ) -> RebalanceListResponse:
        total_count = await get_rebalance_count(db)
        rebalances = await get_rebalances(db, limit=limit, offset=offset)
        
        items = [
            RebalanceListItem.model_validate(r)
            for r in rebalances
        ]
        
        return RebalanceListResponse(
            total_count=total_count,
            items=items,
        )
    
    
    # ⚙️ 리밸런스 상세 조회
    async def get_rebalance_detail(
        self,
        db: AsyncSession,
        rebalance_id: UUID,
    ) -> RebalanceDetailResponse | None:
        rebalance = await get_rebalance_by_id(db, rebalance_id)
        if rebalance is None:
            return None
        
        orders = await get_orders_by_rebalance_id(db, rebalance_id)
        
        order_items = [
            self._build_order_item(order) for order in orders
        ]
        execution_summary = self._build_execution_summary(rebalance, order_items)
        
        return RebalanceDetailResponse(
            id=rebalance.id,
            strategy_name=rebalance.strategy_name,
            screener_name=rebalance.screener_name,
            status=rebalance.status,
            universe_count=rebalance.universe_count,
            buy_signal_count=rebalance.buy_signal_count,
            buy_count=rebalance.buy_count,
            sell_count=rebalance.sell_count,
            hold_count=rebalance.hold_count,
            total_sell_value=rebalance.total_sell_value,
            total_buy_value=rebalance.total_buy_value,
            available_cash_before=rebalance.available_cash_before,
            estimated_cash_after=rebalance.estimated_cash_after,
            dry_run=rebalance.dry_run,
            strategy_params=rebalance.strategy_params,
            executed_at=rebalance.executed_at,
            completed_at=rebalance.completed_at,
            execution_summary=execution_summary,
            orders=order_items,
        )
    
    
    
    # ── private helpers ──
    @staticmethod
    # ⚙️ 종목별 체결 소요시간 계산 (submitted_at → updated_at)
    def _calc_fill_duration_seconds(order: Order) -> float | None:
        """종목별 체결 소요시간 (submitted_at → updated_at)"""
        if order.submitted_at is None or order.updated_at is None:
            return None
        delta: timedelta = order.updated_at - order.submitted_at
        
        # 브로커 서버 타임스탬프와 체결 이벤트 수신 시점 오차가 있을 수 있으므로, 음수인 경우는 0으로 처리(clamping )
        if(delta.total_seconds() < 0):
            return 0.0
        return round(delta.total_seconds(), 2)
    
    
    # ⚙️ 주문 → RebalanceOrderItem 변환
    def _build_order_item(self, order: Order) -> RebalanceOrderItem:
        return RebalanceOrderItem(
            id=order.id,
            stock_code=order.stock_code,
            order_pos=order.order_pos,
            order_type=order.order_type,
            order_qty=order.order_qty,
            filled_qty=order.filled_qty,
            remaining_qty=order.remaining_qty,
            avg_fill_price=order.avg_fill_price,
            status=order.status,
            submitted_at=order.submitted_at,
            updated_at=order.updated_at,
            fill_duration_seconds=self._calc_fill_duration_seconds(order),
        )
    
    
    # ⚙️ 리밸런스 실행 요약 정보 계산
    @staticmethod
    def _build_execution_summary(
        rebalance: Rebalance,
        order_items: list[RebalanceOrderItem],
    ) -> RebalanceExecutionSummary:
        # 편입 실패율
        signal_count = rebalance.buy_signal_count
        filled_count = rebalance.buy_count
        fail_rate = (
            round(1 - (filled_count / signal_count), 4)
            if signal_count > 0
            else 0.0
        )
        
        # 예수금 비율
        cash_before = rebalance.available_cash_before
        cash_after = rebalance.estimated_cash_after
        cash_ratio = None
        if cash_before and cash_before > 0:
            cash_ratio = round(float(cash_after / cash_before), 4)
        
        # 리밸런싱 총 소요시간
        rebalance_duration = None
        if rebalance.completed_at and rebalance.executed_at:
            delta: timedelta = rebalance.completed_at - rebalance.executed_at
            rebalance_duration = round(delta.total_seconds(), 2)
        
        # 평균 체결 소요시간
        durations = [
            item.fill_duration_seconds
            for item in order_items
            if item.fill_duration_seconds is not None
        ]
        avg_fill_duration = (
            round(sum(durations) / len(durations), 2)
            if durations
            else None
        )
        
        # TODO(P1/전략): 성과 분석 지표 구현 — 
        # 포트폴리오 수익률 vs 벤치마크, 
        # 종목별 기여도, 
        # 승률, 
        # 턴오버율, 
        # Alpha/CAGR/MDD/Volatility/Sharpe Ratio (FDR·WebSocket 연동 + 일별 수익률 시계열 누적 후)
        
        return RebalanceExecutionSummary(
            signal_count=signal_count,
            filled_count=filled_count,
            fail_rate=fail_rate,
            available_cash_before=cash_before,
            estimated_cash_after=cash_after,
            cash_ratio=cash_ratio,
            rebalance_duration_seconds=rebalance_duration,
            avg_fill_duration_seconds=avg_fill_duration,
        )