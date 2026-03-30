from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown, worker_ready

from app.utils.logger import get_logger
from app.core.settings import settings
from app.worker.runtime import init_worker_runtime, run_async, shutdown_worker_runtime

logger = get_logger(__name__)

celery_app = Celery(
    "autotrading",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker.tasks_order", "app.worker.tasks_order_status", "app.worker.tasks_recovery"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=False,
    
    # 태스크 라우팅 설정: 주문 처리 태스크는 orders.submit 큐로, 주문 상태 추적 태스크는 orders.track 큐로 라우팅
    task_default_queue="orders.submit",
    task_routes={
        "app.worker.tasks_order.process_order": {"queue": "orders.submit"},
        "app.worker.tasks_order_status.process_order_status": {"queue": "orders.track"},
        "app.worker.tasks_recovery.recover_orders": {"queue": "orders.recovery"},
    },
    
    worker_hijack_root_logger=False,  # Celery가 루트 로거를 가로채지 않도록 설정
    worker_log_format="[%(asctime)s] %(levelname)s %(message)s",
    worker_task_log_format="[%(asctime)s] %(levelname)s [%(task_name)s] %(message)s",
)


# Celery 워커 프로세스가 시작될 때마다 init_worker_runtime()을 호출해서 event loop를 초기화한다.
@worker_process_init.connect
def on_worker_process_init(**kwargs) -> None:
    init_worker_runtime()


# Celery 워커 프로세스가 종료될 때마다 shutdown_worker_runtime()을 호출해서 event loop를 정리한다.
@worker_process_shutdown.connect
def on_worker_process_shutdown(**kwargs) -> None:
    shutdown_worker_runtime()


@worker_ready.connect
def on_worker_ready(sender=None, **kwargs) -> None:
    """
    worker 시작 직후 복구 태스크 1회 등록.

    주의: worker_ready 시그널은 모든 Celery worker 인스턴스에서 발생한다.
    worker_1, worker_2, worker_3가 동시에 뜨면 recover_orders가 중복 enqueue될 수 있으므로,
    복구 전용 worker(hostname=worker3@*)에서만 등록한다.
    """
    hostname = getattr(sender, "hostname", "") or ""
    if not hostname.startswith("worker3@"):
        logger.info(f"복구 태스크 자동 등록 건너뜀. hostname={hostname}")
        return

    from app.worker.tasks_recovery import recover_orders

    logger.info(f"복구 태스크 자동 등록 실행. hostname={hostname}")
    recover_orders.delay()