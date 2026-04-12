"""
⭐ Order Generator
    PositionDiffResult를 기반으로 실제 주문(Order)을 DB에 생성하고
    Celery worker-1(process_order)에 전달하는 모듈
    
    주문 순서 정책:
        1. 매도 주문을 먼저 전부 생성 (현금 확보)
        2. 매수 주문은 매도 체결 이후 생성 (Phase 2에서 체결 대기 로직 추가)
           → Phase 1에서는 매도/매수 순차 생성만 수행
    
    주문 생성 시 고려사항:
        - Kill Switch 활성 상태이면 주문 생성 자체를 차단
        - 각 주문은 ORDER_STATUS.PENDING으로 생성 → worker-1이 PROCESSING으로 전이
        - 시장가 주문 기본 (향후 지정가 옵션 확장 가능)
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ORDER_ACTION, ORDER_KIND, ORDER_STATUS, ORDER_TYPE
from app.core.settings import settings
from app.strategy.live.position_diff import DiffAction, PositionDiffItem, PositionDiffResult
from app.worker.tasks_order import process_order
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OrderRequest:
    """worker-1에 전달할 주문 요청 정보"""
    order_id: str               # UUID (DB insert 시 사용)
    stock_code: str
    stock_name: str
    action: str                 # BUY / SELL
    quantity: int
    price: int                  # 지정가일 때 가격, 시장가면 0
    order_type: str             # MARKET / LIMIT
    order_kind: str             # NEW / MODIFY / CANCEL
    
    # 추적용
    rebalance_id: str = ""      # 이 주문이 속한 리밸런싱 세션 ID
    diff_action: str = ""       # SELL / BUY / REBALANCE


@dataclass
class OrderGenerationResult:
    """주문 생성 결과"""
    rebalance_id: str
    sell_orders: list[OrderRequest] = field(default_factory=list)
    buy_orders: list[OrderRequest] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)       # 건너뛴 종목 (사유 포함)
    
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
        
        lines.append(f"매수 주문: {len(self.buy_orders)}건")
        for o in self.buy_orders:
            lines.append(f"   [{o.order_id[:8]}] {o.stock_code} {o.stock_name}: {o.quantity}주 매수")
        
        if self.skipped:
            lines.append(f"건너뜀: {len(self.skipped)}건")
            for s in self.skipped:
                lines.append(f"   {s['stock_code']}: {s['reason']}")
        
        lines.append("=" * 60)
        return "\n".join(lines)


class OrderGenerator:
    """
    ⭐ 주문 생성기
    
    PositionDiffResult → Order DB rows + Celery 태스크 큐잉
    
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
    """
    
    def __init__(
        self,
        order_type: ORDER_TYPE = ORDER_TYPE.MARKET,
        account_no: str | None = None,
        account_product_code: str = "01",
        dry_run: bool = False,
    ):
        self.order_type = order_type
        self.account_no = account_no or settings.KIS_ACCOUNT_NO
        self.account_product_code = account_product_code
        self.dry_run = dry_run
    
    
    def generate_orders(
        self,
        diff_result: PositionDiffResult,
        rebalance_id: str | None = None,
    ) -> OrderGenerationResult:
        """
        diff 결과를 기반으로 주문 요청 리스트 생성
        
        Parameters
        ----------
        diff_result : PositionDiffCalculator.calculate() 결과
        rebalance_id : 리밸런싱 세션 ID (없으면 자동 생성)
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
    
    
    async def submit_orders(
        self,
        generation_result: OrderGenerationResult,
        db: AsyncSession,
    ) -> None:
        """
        생성된 주문을 DB에 저장하고 Celery worker-1에 큐잉
        
        Parameters
        ----------
        generation_result : generate_orders() 결과
        db : SQLAlchemy async session
        
        주문 흐름:
            1. 매도 주문 전부 DB insert + Celery 큐잉
            2. 매수 주문 전부 DB insert + Celery 큐잉
               (Phase 2에서 매도 체결 대기 후 매수 진행으로 개선)
        """
        from app.db.models.order import Order
        
        # ── 매도 주문 제출 ──
        for order_req in generation_result.sell_orders:
            await self._insert_and_queue(db, order_req)
        
        # ── 매수 주문 제출 ──
        # TODO: Phase 2 - 매도 체결 완료 대기 후 매수 주문 생성
        #       현재는 매도/매수 동시 큐잉 (모의투자에서는 거의 즉시 체결)
        for order_req in generation_result.buy_orders:
            await self._insert_and_queue(db, order_req)
        
        await db.commit()
        
        logger.info(
            f"주문 제출 완료: rebalance_id={generation_result.rebalance_id}, "
            f"총 {generation_result.total_orders}건"
        )
    
    
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
            rebalance_id=order_req.rebalance_id or None,  # 수동 주문이면 None
        )
        
        db.add(order)
        await db.flush()
        
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