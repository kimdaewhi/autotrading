import json
import redis.asyncio as redis

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.websocket.serializers import serialize_order_ws_payload
from app.repository.order_repository import get_order_by_id

ORDER_WS_CHANNEL = "order_updates"


# ⚙️ Redis Pub/Sub 채널로 주문 업데이트 메시지 발행
async def _publish_message(message: dict) -> None:
    redis_client = redis.from_url(
        settings.CELERY_BROKER_URL,
        decode_responses=True,
    )
    try:
        await redis_client.publish(
            ORDER_WS_CHANNEL,
            json.dumps(message, ensure_ascii=False, default=str),
        )
    finally:
        await redis_client.close()



async def publish_order_update(
    db: AsyncSession,
    order_id: UUID,
    include_parent: bool = True,
) -> None:
    """
    주문 업데이트 이벤트를 Redis Pub/Sub 채널로 발행
    - worker / router 어디서 호출하든 동일하게 동작
    """

    # 1. 현재 주문
    order = await get_order_by_id(db, order_id)
    if order:
        await _publish_message(
            {
                "type": "order_updated",
                "data": serialize_order_ws_payload(order),
            }
        )

    # 2. 부모 주문도 함께 발행
    if include_parent and order and order.original_order_id:
        parent_order = await get_order_by_id(db, order.original_order_id)
        if parent_order:
            await _publish_message(
                {
                    "type": "order_updated",
                    "data": serialize_order_ws_payload(parent_order),
                }
            )