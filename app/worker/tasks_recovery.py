from app.worker.celery_app import celery_app
from app.worker.runtime import run_async
from app.worker.recovery import recover_all_orders
from app.utils.logger import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.worker.tasks_recovery.recover_orders")
def recover_orders() -> None:
    logger.info("재기동 복구 태스크 시작")
    run_async(recover_all_orders())
    logger.info("재기동 복구 태스크 종료")