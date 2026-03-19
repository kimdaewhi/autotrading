from celery import Celery

celery_app = Celery(
    "autotrading",
    broker="redis://localhost:6380/0",
    backend="redis://localhost:6380/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=False,
)

import app.broker.tasks