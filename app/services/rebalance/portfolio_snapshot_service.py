import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.snapshot import PortfolioSnapshot, PortfolioSnapshotHolding
from app.repository.portfolio_snapshot_repository import (
    get_snapshot_id_by_rebalance,
    insert_snapshot,
)
from app.services.kis.account_service import AccountService
from app.strategy.runtime.position_diff import DiffAction
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PortfolioSnapshotService:
    """리밸런스/일별 시점의 포트폴리오를 캡쳐한다."""
    
    def __init__(self, account_service: AccountService):
        self._account_service = account_service
        
    async def capture(
        self,
        db: AsyncSession,
        rebalance_id: str,
        snapshot_type: DiffAction,
    ) -> str:
        """현재 계좌 보유 현황을 조회해 스냅샷으로 저장.
        
        Returns:
            생성된 snapshot_id. 이미 존재하면 기존 id (멱등).
        """
        # 1. 멱등성 — 이미 이 rebalance_id의 스냅샷이 있으면 skip
        existing = await get_snapshot_id_by_rebalance(db, rebalance_id)
        if existing is not None:
            logger.info("스냅샷 이미 존재 — skip. rebalance_id=%s", rebalance_id)
            return existing
        
        # 2. KIS 실계좌 조회 (도메인 로직)
        holdings_raw = await self._account_service.get_holding_list()
        summary = await self._account_service.get_account_summary()
        
        # 3. 엔티티 구성 (가공 — 문자열 → int/Decimal 변환)
        snapshot_id = uuid.uuid4()
        snapshot = PortfolioSnapshot(
            id=snapshot_id,
            snapshot_at=datetime.now(timezone.utc),
            snapshot_type=snapshot_type.value,
            rebalance_id=rebalance_id,
            cash_amount=int(summary.cash_amount),
        )
        holdings = [
            PortfolioSnapshotHolding(
                id=uuid.uuid4(),
                snapshot_id=snapshot_id,
                stock_code=h.stock_code,
                stock_name=h.stock_name,
                holding_qty=int(h.holding_qty),
                avg_buy_price=Decimal(h.avg_buy_price),
            )
            for h in holdings_raw
        ]
        
        # 4. 저장
        await insert_snapshot(db, snapshot, holdings)
        await db.commit()
        
        logger.info(
            "포트폴리오 스냅샷 저장. rebalance_id=%s, snapshot_id=%s, %d종목",
            rebalance_id, snapshot_id, len(holdings),
        )
        return snapshot_id