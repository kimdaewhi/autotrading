"""
⭐ Order Generator
    PositionDiffResult를 기반으로 실제 주문(Order)을 DB에 생성하고
    Celery worker-1(process_order)에 전달하는 모듈
    
    주문 순서 정책:
        1. 매도 주문을 먼저 전부 큐잉 (현금 확보)
        2. 매도 체결 완료 대기 (타임아웃 시 미체결 잔량 취소)
        3. 실제 확보된 현금 기준으로 매수 금액 재계산
        4. 매수 주문 큐잉
        5. 매수 체결 완료 대기 (타임아웃 시 미체결 잔량 취소)
    
    주문 생성 시 고려사항:
        - Kill Switch 활성 상태이면 주문 생성 자체를 차단
        - 각 주문은 ORDER_STATUS.PENDING으로 생성 → worker-1이 PROCESSING으로 전이
        - 시장가 주문 기본 (향후 지정가 옵션 확장 가능)
"""

import asyncio
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.strategy.rebalance import OrderRequest, FillResult, OrderGenerationResult
from app.core.constants import FILL_POLL_FAST_INTERVAL, FILL_POLL_FAST_WINDOW, FILL_POLL_SLOW_INTERVAL, FILL_TIMEOUT_SECONDS
from app.core.enums import ORDER_ACTION, ORDER_KIND, ORDER_STATUS, ORDER_TYPE
from app.core.settings import settings
from app.strategy.live.position_diff import DiffAction, PositionDiffItem, PositionDiffResult
from app.worker.tasks_order import process_order
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 주문 최종 상태 집합
TERMINAL_STATUSES = {
    ORDER_STATUS.FILLED.value,
    ORDER_STATUS.FAILED.value,
    ORDER_STATUS.CANCELED.value,
}


class OrderGenerator:
    """
    ⭐ 주문 생성기
    
    PositionDiffResult → Order DB rows + Celery 태스크 큐잉
    매도 체결 완료 대기 후 매수 주문 생성
    
    Parameters
    ----------
    order_type : ORDER_TYPE
        주문 가격 유형 (기본: 시장가)
    account_no : str
        계좌번호 (settings에서 가져옴)
    account_product_code : str
        계좌 상품코드 (기본: "01")
    dry_run : bool
        True면 주문 생성만 하고 실제 Celery 큐잉은 하지 않음 (검증용)
    fill_timeout_seconds : int
        체결 대기 타임아웃 (초, 기본 15분)
    """
    
    def __init__(
        self,
        order_type: ORDER_TYPE = ORDER_TYPE.MARKET,
        account_no: str | None = None,
        account_product_code: str = "01",
        dry_run: bool = False,
        fill_timeout_seconds: int = FILL_TIMEOUT_SECONDS,
    ):
        self.order_type = order_type
        self.account_no = account_no or settings.KIS_ACCOUNT_NO
        self.account_product_code = account_product_code
        self.dry_run = dry_run
        self.fill_timeout_seconds = fill_timeout_seconds
    
    
    # ⚙️ 리밸런싱 주문지 생성 (매도/매수 분리)
    def generate_orders(
        self,
        diff_result: PositionDiffResult,
        rebalance_id: str | None = None,
    ) -> OrderGenerationResult:
        """
        diff 결과를 기반으로 주문 요청 리스트 생성
        """
        rebalance_id = rebalance_id or str(uuid.uuid4())
        
        result = OrderGenerationResult(rebalance_id=rebalance_id)
        
        # ── 1. 매도 주문 생성 (현금 확보 우선) ──
        for item in diff_result.sell_list:
            order_req = self._create_order_request(
                item=item,
                action=ORDER_ACTION.SELL,
                rebalance_id=rebalance_id,
            )
            if order_req:
                result.sell_orders.append(order_req)
            else:
                result.skipped.append({
                    "stock_code": item.stock_code,
                    "reason": "매도 주문 생성 실패 (수량 0 또는 검증 실패)",
                })
        
        # ── 2. 매수 주문 생성 ──
        for item in diff_result.buy_list:
            order_req = self._create_order_request(
                item=item,
                action=ORDER_ACTION.BUY,
                rebalance_id=rebalance_id,
            )
            if order_req:
                result.buy_orders.append(order_req)
            else:
                result.skipped.append({
                    "stock_code": item.stock_code,
                    "reason": "매수 주문 생성 실패 (수량 0 또는 검증 실패)",
                })
        
        logger.info(
            f"주문 생성 완료: rebalance_id={rebalance_id}, "
            f"매도 {len(result.sell_orders)}건, 매수 {len(result.buy_orders)}건, "
            f"건너뜀 {len(result.skipped)}건"
        )
        
        return result
    
    
    # ⚙️ 주문 제출 (매도 체결 대기 → 매수 금액 재계산 → 매수 제출)
    async def submit_orders(
        self,
        generation_result: OrderGenerationResult,
        db: AsyncSession,
        account_service=None,
        buy_codes: list[str] | None = None,
        signal_df=None,
        hold_list=None,
        price_map: dict[str, int] | None = None,
        name_map: dict[str, str] | None = None,
    ) -> None:
        """
        생성된 주문을 DB에 저장하고 Celery worker-1에 큐잉
        매도 체결 완료를 기다린 후 매수 주문을 진행
        
        Parameters
        ----------
        generation_result : generate_orders() 결과
        db : SQLAlchemy async session
        account_service : AccountService (매도 체결 후 실제 예수금 조회용, None이면 예상 금액 사용)
        buy_codes : 매수 대상 종목 코드 (매수 금액 재계산용)
        signal_df : 전략 시그널 DataFrame (매수 금액 재계산용)
        hold_list : 유지 종목 리스트 (매수 금액 재계산용)
        price_map : {종목코드: 매매기준가} (매수 금액 재계산용)
        name_map : {종목코드: 종목명} (매수 금액 재계산용)
        """
        # ── 1단계: 매도 주문 제출 ──
        sell_order_ids = []
        for order_req in generation_result.sell_orders:
            await self._insert_and_queue(db, order_req)
            sell_order_ids.append(order_req.order_id)
        
        logger.info(
            f"매도 주문 제출 완료: {len(sell_order_ids)}건, "
            f"rebalance_id={generation_result.rebalance_id}"
        )
        
        # ── 2단계: 매도 체결 대기 ──
        if sell_order_ids and not self.dry_run:
            sell_fill_result = await self._wait_for_fills(
                db=db,
                order_ids=sell_order_ids,
                phase="매도",
            )
            generation_result.sell_fill_result = sell_fill_result
            
            logger.info(
                f"매도 체결 대기 완료: "
                f"체결 {sell_fill_result.filled_orders}/{sell_fill_result.total_orders}건, "
                f"체결금액 {sell_fill_result.total_filled_amount:,}원"
                f"{' (타임아웃 발생)' if sell_fill_result.timed_out else ''}"
            )
        
        # TODO : 매도 또는 매수가 실패처리 난 주문에 대해 재시도 정책은 어떻게 할지 고민 (예: 매도 실패 → 매수도 취소 or 재시도)
        
        # ── 3단계: 매수 금액 재계산 (실제 확보 현금 기준) ──
        if not self.dry_run and account_service and buy_codes and price_map:
            actual_cash = await self._get_actual_cash(account_service)
            
            logger.info(f"매도 체결 후 실제 예수금: {actual_cash:,}원")
            
            generation_result.buy_orders = self._recalculate_buy_orders(
                available_cash=actual_cash,
                buy_codes=buy_codes,
                signal_df=signal_df,
                hold_list=hold_list or [],
                price_map=price_map,
                name_map=name_map or {},
                rebalance_id=generation_result.rebalance_id,
            )
            
            logger.info(f"매수 주문 재계산 완료: {len(generation_result.buy_orders)}건")
        
        # ── 4단계: 매수 주문 제출 ──
        buy_order_ids = []
        for order_req in generation_result.buy_orders:
            await self._insert_and_queue(db, order_req)
            buy_order_ids.append(order_req.order_id)
        
        logger.info(
            f"매수 주문 제출 완료: {len(buy_order_ids)}건, "
            f"rebalance_id={generation_result.rebalance_id}"
        )
        
        # ── 5단계: 매수 체결 대기 ──
        if buy_order_ids and not self.dry_run:
            buy_fill_result = await self._wait_for_fills(
                db=db,
                order_ids=buy_order_ids,
                phase="매수",
            )
            generation_result.buy_fill_result = buy_fill_result
            
            logger.info(
                f"매수 체결 대기 완료: "
                f"체결 {buy_fill_result.filled_orders}/{buy_fill_result.total_orders}건"
                f"{' (타임아웃 발생)' if buy_fill_result.timed_out else ''}"
            )
        
        logger.info(
            f"주문 제출 완료: rebalance_id={generation_result.rebalance_id}, "
            f"총 {generation_result.total_orders}건"
        )
    
    
    # ⚙️ 체결 대기 폴링 (빠른 구간 → 느린 구간 → 타임아웃 시 잔량 취소)
    async def _wait_for_fills(
        self,
        db: AsyncSession,
        order_ids: list[str],
        phase: str = "",
    ) -> FillResult:
        """
        주문 리스트의 체결 완료를 폴링으로 대기
        타임아웃 시 미체결 주문은 취소 요청
        
        폴링 정책 (tasks_order_status 참고):
            - 0~90초: 빠른 폴링 (3초 간격)
            - 90초~: 느린 폴링 (15초 간격)
            - 15분 초과: 타임아웃 → 미체결 잔량 취소
        """
        from app.db.models.order import Order
        
        start_time = datetime.now(timezone.utc)
        result = FillResult(total_orders=len(order_ids))
        
        while True:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # 타임아웃 체크
            if elapsed >= self.fill_timeout_seconds:
                result.timed_out = True
                logger.warning(
                    f"[{phase}] 체결 대기 타임아웃 ({self.fill_timeout_seconds}초). "
                    f"미체결 주문 취소 진행"
                )
                break
            
            # DB에서 주문 상태 일괄 조회
            db.expire_all()
            query = select(Order).where(Order.id.in_(order_ids))
            rows = (await db.execute(query)).scalars().all()
            
            # 종료 상태 집계
            filled = 0
            canceled = 0
            failed = 0
            total_filled_amount = 0
            all_terminal = True
            
            for order in rows:
                if order.status == ORDER_STATUS.FILLED.value:
                    filled += 1
                    total_filled_amount += int(
                        (order.avg_fill_price or 0) * (order.filled_qty or 0)
                    )
                elif order.status == ORDER_STATUS.CANCELED.value:
                    canceled += 1
                    total_filled_amount += int(
                        (order.avg_fill_price or 0) * (order.filled_qty or 0)
                    )
                elif order.status == ORDER_STATUS.FAILED.value:
                    failed += 1
                else:
                    all_terminal = False
            
            result.filled_orders = filled
            result.canceled_orders = canceled
            result.failed_orders = failed
            result.total_filled_amount = total_filled_amount
            
            # 전부 종료 상태이면 대기 종료
            if all_terminal:
                logger.info(
                    f"[{phase}] 전체 주문 종료: "
                    f"체결 {filled}, 취소 {canceled}, 실패 {failed} "
                    f"(경과: {elapsed:.0f}초)"
                )
                break
            
            # 폴링 간격 결정 (빠른 구간 vs 느린 구간)
            if elapsed < FILL_POLL_FAST_WINDOW:
                interval = FILL_POLL_FAST_INTERVAL
            else:
                interval = FILL_POLL_SLOW_INTERVAL
            
            pending_count = len(order_ids) - filled - canceled - failed
            logger.info(
                f"[{phase}] 체결 대기 중: "
                f"체결 {filled}, 미체결 {pending_count}, 실패 {failed} "
                f"(경과: {elapsed:.0f}초, 다음 조회: {interval}초 후)"
            )
            
            await asyncio.sleep(interval)
        
        # 타임아웃 시 미체결 주문 취소
        if result.timed_out:
            result.canceled_by_timeout = await self._cancel_unfilled_orders(
                db=db,
                order_ids=order_ids,
                phase=phase,
            )
        
        return result
    
    
    # ⚙️ 미체결 주문 취소 (타임아웃 시 호출)
    async def _cancel_unfilled_orders(
        self,
        db: AsyncSession,
        order_ids: list[str],
        phase: str = "",
    ) -> int:
        """
        미체결 주문에 대해 취소 주문 생성 + worker-1 큐잉
        
        Returns
        -------
        int : 취소 요청한 주문 수
        """
        from app.db.models.order import Order
        
        db.expire_all()
        query = select(Order).where(Order.id.in_(order_ids))
        rows = (await db.execute(query)).scalars().all()
        
        cancel_count = 0
        for order in rows:
            # 종료 상태가 아닌 주문만 취소
            if order.status in TERMINAL_STATUSES:
                continue
            
            remaining = order.remaining_qty or order.order_qty
            if remaining <= 0:
                continue
            
            # 취소 주문 생성
            cancel_order_id = str(uuid.uuid4())
            cancel_order = Order(
                id=cancel_order_id,
                stock_code=order.stock_code,
                order_pos=order.order_pos,
                order_qty=remaining,
                order_price=0,
                order_type=ORDER_TYPE.MARKET.value,
                order_kind=ORDER_KIND.CANCEL.value,
                status=ORDER_STATUS.PENDING.value,
                account_no=order.account_no,
                account_product_code=order.account_product_code,
                rebalance_id=order.rebalance_id,
                original_order_id=order.id,
                original_broker_order_no=order.broker_order_no,
                original_broker_org_no=order.broker_org_no,
            )
            
            db.add(cancel_order)
            await db.flush()
            
            process_order.delay(cancel_order_id)
            cancel_count += 1
            
            logger.info(
                f"[{phase}] 미체결 취소 요청: {order.stock_code} "
                f"잔량 {remaining}주 (원주문: {str(order.id)[:8]})"
            )
        
        await db.commit()
        
        logger.info(f"[{phase}] 미체결 취소 완료: {cancel_count}건")
        return cancel_count
    
    
    # ⚙️ 실제 예수금 조회 (매도 체결 후)
    async def _get_actual_cash(self, account_service) -> int:
        """매도 체결 후 실제 예수금을 KIS 계좌 API로 조회"""
        try:
            summary = await account_service.get_account_summary()
            return int(summary.cash_amount)
        except Exception as e:
            logger.warning(f"예수금 조회 실패, 0으로 처리: {e}")
            return 0
    
    
    # ⚙️ 매수 주문 재계산 (실제 확보 현금 기준)
    def _recalculate_buy_orders(
        self,
        available_cash: int,
        buy_codes: list[str],
        signal_df,
        hold_list: list,
        price_map: dict[str, int],
        name_map: dict[str, str],
        rebalance_id: str,
    ) -> list[OrderRequest]:
        """
        실제 확보된 현금을 기준으로 매수 주문 수량을 재계산
        position_diff의 균등 비중 로직과 동일한 방식
        """
        if available_cash <= 0 or not buy_codes:
            logger.warning("매수 가능 현금 없음 - 매수 주문 생성 건너뜀")
            return []
        
        # 유지 종목 평가액
        hold_value = sum(
            item.current_value for item in hold_list
        ) if hold_list else 0
        
        # 균등 비중 계산
        total_portfolio_value = available_cash + hold_value
        target_per_stock = total_portfolio_value / len(buy_codes) if buy_codes else 0
        
        # 신규 매수 종목만 (보유 중인 건 제외)
        holding_codes = {item.stock_code for item in hold_list} if hold_list else set()
        new_buy_codes = [c for c in buy_codes if c not in holding_codes]
        
        if not new_buy_codes:
            return []
        
        total_new_buy_target = target_per_stock * len(new_buy_codes)
        actual_budget = min(total_new_buy_target, available_cash)
        alloc_per_stock = actual_budget / len(new_buy_codes)
        
        buy_orders = []
        for code in new_buy_codes:
            price = price_map.get(code, 0)
            if price <= 0:
                continue
            
            qty = math.floor(alloc_per_stock / price)
            if qty <= 0:
                continue
            
            # 모멘텀 부가 정보
            momentum_return = 0.0
            momentum_rank = 0
            if signal_df is not None and code in signal_df.index:
                momentum_return = float(signal_df.loc[code, "return"])
                momentum_rank = int(signal_df.loc[code, "rank"])
            
            order_price = 0 if self.order_type == ORDER_TYPE.MARKET else price
            
            order_req = OrderRequest(
                order_id=str(uuid.uuid4()),
                stock_code=code,
                stock_name=name_map.get(code, code),
                action=ORDER_ACTION.BUY.value,
                quantity=qty,
                price=order_price,
                order_type=self.order_type.value,
                order_kind=ORDER_KIND.NEW.value,
                rebalance_id=rebalance_id,
                diff_action=DiffAction.BUY.value,
            )
            buy_orders.append(order_req)
        
        logger.info(
            f"매수 주문 재계산: 예수금 {available_cash:,}원, "
            f"종목당 배분 {alloc_per_stock:,.0f}원, "
            f"{len(buy_orders)}종목 매수 가능"
        )
        
        return buy_orders
    
    
    # ⚙️ 개별 종목 주문 요청 생성
    def _create_order_request(
        self,
        item: PositionDiffItem,
        action: ORDER_ACTION,
        rebalance_id: str,
    ) -> OrderRequest | None:
        """개별 종목에 대한 주문 요청 생성"""
        if item.order_qty <= 0:
            return None
        
        price = 0 if self.order_type == ORDER_TYPE.MARKET else item.current_price
        
        return OrderRequest(
            order_id=str(uuid.uuid4()),
            stock_code=item.stock_code,
            stock_name=item.stock_name,
            action=action.value,
            quantity=item.order_qty,
            price=price,
            order_type=self.order_type.value,
            order_kind=ORDER_KIND.NEW.value,
            rebalance_id=rebalance_id,
            diff_action=item.action.value,
        )
    
    
    # ⚙️ 단건 주문 DB 저장 + Celery 큐잉
    async def _insert_and_queue(
        self,
        db: AsyncSession,
        order_req: OrderRequest,
    ) -> None:
        """단건 주문 DB insert + Celery 큐잉"""
        from app.db.models.order import Order
        
        order = Order(
            id=order_req.order_id,
            stock_code=order_req.stock_code,
            order_pos=order_req.action,
            order_qty=order_req.quantity,
            order_price=order_req.price,
            order_type=order_req.order_type,
            order_kind=order_req.order_kind,
            status=ORDER_STATUS.PENDING.value,
            account_no=self.account_no,
            account_product_code=self.account_product_code,
            rebalance_id=order_req.rebalance_id or None,
        )
        
        db.add(order)
        await db.commit()
        
        if not self.dry_run:
            process_order.delay(order_req.order_id)
            logger.info(
                f"주문 큐잉: [{order_req.action}] {order_req.stock_code} "
                f"{order_req.stock_name} {order_req.quantity}주 "
                f"(order_id={order_req.order_id[:8]}, rebalance_id={order_req.rebalance_id[:8]})"
            )
        else:
            logger.info(
                f"[DRY_RUN] 주문 생성만: [{order_req.action}] {order_req.stock_code} "
                f"{order_req.stock_name} {order_req.quantity}주"
            )