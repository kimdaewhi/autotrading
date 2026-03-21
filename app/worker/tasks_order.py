from app.worker.celery_app import celery_app
from app.utils.logger import get_logger

logger = get_logger(__name__)

@celery_app.task(name="app.worker.tasks_order.test_task")
def test_task(message: str) -> str:
    logger.info(f"[Celery Task] message={message}")
    return f"done: {message}"


@celery_app.task(name="app.worker.tasks_order.process_order")
def process_order(order_id: str) -> None:
    # 여기서는 일단 호출 확인만
    logger.info(f"주문 메시지큐 등록 테스트 order_id={order_id}")

    # 1. DB에서 order_id 조회
    
    # 2. status 검사
    
    # 3. 한투 주문 실행
    
    # 4. 결과 DB 업데이트