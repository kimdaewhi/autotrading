import redis.asyncio as redis

from app.broker.kis.kis_account import KISAccount
from app.core.settings import settings
from app.db.session import AsyncSessionLocal
from app.services.kis.account_service import AccountService
from app.services.rebalance.portfolio_snapshot_service import PortfolioSnapshotService
from app.strategy.runtime.position_diff import DiffAction
from app.utils.logger import get_logger
from app.worker.celery_app import celery_app
from app.worker.runtime import run_async

logger = get_logger(__name__)


@celery_app.task(name="app.worker.tasks_snapshot.capture_rebalance_snapshot")
def capture_rebalance_snapshot(rebalance_id: str) -> None:
    run_async(_capture_rebalance_snapshot(rebalance_id))


async def _capture_rebalance_snapshot(rebalance_id: str) -> None:
    """
    리밸런스에 속한 모든 주문이 terminal 상태에 도달한 뒤 worker-2에서 큐잉된다.
    체결이 반영된 시점의 계좌 보유 현황을 조회해 포트폴리오 스냅샷으로 저장한다.
    
    - capture()가 rebalance_id 기준으로 멱등하므로 중복 큐잉되어도 안전하다.
    - 스냅샷 실패는 리밸런스/주문 결과에 영향을 주지 않는다. (백필로 보완 가능)
    """
    async with AsyncSessionLocal() as db:
        try:
            account_service = AccountService(
                kis_account=KISAccount(
                    appkey=settings.KIS_APP_KEY,
                    appsecret=settings.KIS_APP_SECRET,
                    url=f"{settings.kis_base_url}",
                )
            )
            
            snapshot_service = PortfolioSnapshotService(account_service)
            snapshot_id = await snapshot_service.capture(
                db=db,
                rebalance_id=rebalance_id,
                snapshot_type=DiffAction.REBALANCE,
            )
            
            logger.info(f"포트폴리오 스냅샷 저장 완료. rebalance_id : {rebalance_id}, "f"snapshot_id : {snapshot_id}")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"포트폴리오 스냅샷 저장 실패. rebalance_id : {rebalance_id}, error : {e}", exc_info=True,)