from celery import Celery
from app.utils.logger import get_logger
from app.core.settings import settings

logger = get_logger(__name__)

celery_app = Celery(
    "autotrading",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker.tasks_order", "app.worker.tasks_order_status"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=False,
    
    worker_hijack_root_logger=False,  # Celery가 루트 로거를 가로채지 않도록 설정
    worker_log_format="[%(asctime)s] %(levelname)s %(message)s",
    worker_task_log_format="[%(asctime)s] %(levelname)s [%(task_name)s] %(message)s",
)