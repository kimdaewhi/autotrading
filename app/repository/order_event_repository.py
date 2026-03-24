from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.order_event import OrderEvent


# ⚙️ 주문 이벤트 로그 생성 함수
async def create_order_event(
    db: AsyncSession,
    order_id: UUID,
    event_type: str,
    event_provider: str,
    message: str | None = None,
    payload: dict | None = None,
) -> OrderEvent:
    """
    주문 이벤트 로그 생성 (insert only)
    """
    event = OrderEvent(
        order_id=order_id,
        event_type=event_type,
        event_provider=event_provider,
        message=message,
        payload=payload,
    )

    db.add(event)
    await db.flush()
    await db.refresh(event)

    return event