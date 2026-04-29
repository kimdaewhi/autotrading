from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import REBALANCE_STATUS
from app.db.models.rebalance import Rebalance
from app.schemas.strategy.trading import (
    StrategyResult,
    RebalanceResult,
    CurrentHolding,
    TradeSide,
)
from app.services.kis.account_service import AccountService
from app.strategy.runtime.position_diff import PositionDiffCalculator
from app.strategy.runtime.order_generator import OrderGenerator
from app.strategy.runtime.base_executor import BaseExecutor
from app.utils.discord import send_rebalance_alert
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RebalanceExecutor(BaseExecutor):
    """
    포트폴리오 리밸런싱 실행기

    Strategy가 반환한 StrategyResult(TradeIntent 리스트)를 받아
    계좌 조회 → diff 계산 → 주문 생성/제출을 처리한다.
    """

    def __init__(
        self,
        account_service: AccountService,
        diff_calculator: PositionDiffCalculator | None = None,
        order_generator: OrderGenerator | None = None,
    ):
        self.account_service = account_service
        self.diff_calculator = diff_calculator or PositionDiffCalculator()
        self.order_generator = order_generator or OrderGenerator()

    # ⚙️ BaseExecutor 구현, 전략 결과를 받아 주문 실행
    async def submit(
        self,
        result: StrategyResult,
        db: AsyncSession,
        dry_run: bool = True,
    ) -> RebalanceResult:
        import uuid
        
        rebalance_id = str(uuid.uuid4())
        rebalance_result = RebalanceResult(
            rebalance_id=rebalance_id,
            executed_at=datetime.now().isoformat(),
            dry_run=dry_run,
        )
        
        try:
            # ── TradeIntent에서 매수 종목 정보 추출 ──
            buy_intents = [o for o in result.orders if o.side == TradeSide.BUY]
            buy_codes = [o.stock_code for o in buy_intents]
            name_map = {o.stock_code: o.stock_name for o in buy_intents}
            price_map = {
                o.stock_code: o.price_hint
                for o in buy_intents
                if o.price_hint is not None
            }
            
            rebalance_result.universe_count = result.metadata.get("universe_count", 0)
            rebalance_result.signal_buy_count = len(buy_codes)
            
            
            # ⭐ 3단계: 현재 보유 포트폴리오 조회
            logger.info("[RebalanceExecutor] 계좌 보유 현황 조회")
            
            holdings_raw = await self.account_service.get_holding_list()
            current_holdings = [
                CurrentHolding(
                    stock_code=h.stock_code,
                    stock_name=h.stock_name,
                    quantity=int(h.holding_qty),
                    current_price=int(h.current_price),
                    eval_amount=int(h.evaluation_amount),
                )
                for h in holdings_raw
            ]
            
            account_summary = await self.account_service.get_account_summary()
            available_cash = int(account_summary.cash_amount)
            
            logger.info(
                f"[RebalanceExecutor] 보유: {len(current_holdings)}종목, "
                f"예수금: {available_cash:,}원"
            )
            
            
            # ⭐ 4단계: 포지션 diff 계산
            logger.info("[RebalanceExecutor] 포지션 diff 계산")
            
            diff_result = self.diff_calculator.calculate(
                buy_codes=buy_codes,
                trade_intents=result.orders,  # TradeIntent 리스트 전체 전달 (매수/매도 시그널 + 매매 가격 정보 포함)
                current_holdings=current_holdings,
                available_cash=available_cash,
                price_map=price_map,
                name_map=name_map,
            )
            rebalance_result.diff_result = diff_result
            
            logger.info(f"\n{diff_result.summary()}")
            
            # dry_run이면 여기서 종료
            if dry_run:
                rebalance_result.success = True
                logger.info("[RebalanceExecutor] DRY RUN 완료")
                return rebalance_result
            
            
            # ⭐ 5단계: 주문 생성 + Celery 큐잉 + Rebalance 기록
            logger.info("[RebalanceExecutor] 주문 생성 및 제출")
            
            # Rebalance 세션 기록
            rebalance_record = Rebalance(
                id=rebalance_id,
                strategy_name=result.strategy_name,
                screener_name=result.metadata.get("screener_name", None),
                universe_count=rebalance_result.universe_count,
                buy_signal_count=rebalance_result.signal_buy_count,
                sell_count=len(diff_result.sell_list),
                buy_count=len(diff_result.buy_list),
                hold_count=len(diff_result.hold_list),
                total_sell_value=diff_result.total_sell_value,
                total_buy_value=diff_result.total_buy_value,
                available_cash_before=available_cash,
                estimated_cash_after=diff_result.estimated_cash_after,
                dry_run=dry_run,
                status=REBALANCE_STATUS.RUNNING.value,
                strategy_params=result.metadata.get("strategy_params", {}),
            )
            db.add(rebalance_record)
            await db.flush()
            
            # 주문 생성 + 큐잉
            order_result = self.order_generator.generate_orders(
                diff_result=diff_result,
                rebalance_id=rebalance_id,
            )
            rebalance_result.order_result = order_result
            
            await self.order_generator.submit_orders(
                generation_result=order_result,
                db=db,
                account_service=self.account_service,
                buy_codes=buy_codes,
                trade_intents=result.orders,  # TradeIntent 리스트 전체 전달 (매수/매도 시그널 + 매매 가격 정보 포함)
                hold_list=diff_result.hold_list,
                price_map=price_map,
                name_map=name_map,
            )
            
            # Rebalance 상태 완료
            rebalance_record.status = REBALANCE_STATUS.COMPLETED.value
            rebalance_record.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            rebalance_result.success = True
            logger.info(
                f"[RebalanceExecutor] 완료: {order_result.total_orders}건 주문 제출"
            )
        
        except Exception as e:
            rebalance_result.error_message = str(e)
            logger.error(f"[RebalanceExecutor] 실패: {e}", exc_info=True)
            
            if db is not None:
                try:
                    from sqlalchemy import update
                    await db.execute(
                        update(Rebalance)
                        .where(Rebalance.id == rebalance_id)
                        .values(status=REBALANCE_STATUS.FAILED.value, error_message=str(e))
                    )
                    await db.commit()
                except Exception:
                    pass
        
        await send_rebalance_alert(rebalance_result)
        return rebalance_result