from app.broker.celery_app import celery_app


@celery_app.task(name="app.broker.tasks.test_task")
def test_task(message: str) -> str:
    print(f"[Celery Task] message={message}")
    return f"done: {message}"