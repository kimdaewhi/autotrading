from celery import Celery
from app.utils.logger import get_logger

logger = get_logger(__name__)

celery_app = Celery(
    "autotrading",
    broker="redis://localhost:6380/0",
    backend="redis://localhost:6380/0",
    include=["app.worker.tasks_order"]
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