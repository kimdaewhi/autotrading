from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.websocket import ws_manager
from app.websocket.serializers import serialize_order_ws_payload
from app.repository.order_repository import get_order_by_id


"""
웹소켓 퍼블리셔
- 필요한 데이터만 조회해서 웹소켓 브로드캐스트
"""

async def publish_order_update(
    db: AsyncSession,
    order_id: UUID,
    include_parent: bool = True,
) -> None:
    """
    주문 업데이트 웹소켓 전파
    
    - order_id 기준으로 최신 주문 조회 후 broadcast
    - include_parent=True이면 부모 주문도 함께 broadcast
    """
    
    # 1. 현재 주문
    order = await get_order_by_id(db, order_id)
    if order:
        await ws_manager.broadcast_order_updated(
            serialize_order_ws_payload(order)
        )
    
    # 2. 원주문 존재하면 원주문도 함께 브로드캐스트
    if include_parent and order and order.original_order_id:
        parent_order = await get_order_by_id(db, order.original_order_id)
        if parent_order:
            await ws_manager.broadcast_order_updated(
                serialize_order_ws_payload(parent_order)
            )