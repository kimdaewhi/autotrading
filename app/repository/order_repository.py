from datetime import datetime
from uuid import UUID
from sqlalchemy import func, update, select
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import Sequence

from app.db.models.order import Order
from app.core.enums import ORDER_STATUS

async def create_order(db: AsyncSession, order_data: dict) -> Order:
    """
    주문 레코드 생성 및 DB 저장
    """
    new_order = Order(**order_data)
    
    db.add(new_order)
    await db.flush()  # 새로 생성된 객체의 ID를 가져오기 위해 flush() 호출
    await db.refresh(new_order)  # 새로 생성된 객체의 상태를 최신으로 유지하기 위해 refresh() 호출
    
    return new_order


async def get_order_by_id(db: AsyncSession, order_id: UUID) -> Order | None:
    """
    주문 ID로 주문 레코드 조회
    """
    stmt = select(Order).where(Order.id == order_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_order_status(db: AsyncSession, order_id: UUID, expected_current_statuses: Sequence[ORDER_STATUS], new_status: ORDER_STATUS,) -> bool:
    """
    주문 상태 업데이트
    - order_id에 해당하는 주문 레코드의 상태가 expected_current_statuses 중 하나인 경우에만 new_status로 업데이트
    """
    stmt = (
        update(Order)
        .where(
            Order.id == order_id,
            Order.status.in_([status.value for status in expected_current_statuses]),
        )
        .values(
            status=new_status.value,
            updated_at=func.now(),
        )
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


async def update_order_submit_result(
    db: AsyncSession, 
    order_id: UUID, 
    rt_cd: str, 
    msg_cd: str, 
    msg1: str, 
    broker_org_no: str, 
    broker_order_no: str, 
    submitted_at: datetime, 
    submit_response_payload: str, 
    next_status: ORDER_STATUS
) -> bool:
    """
    주문 체결 결과 업데이트
    - 주문이 체결된 경우 broker_org_no, broker_order_no, submit_response_payload 등의 필드를 업데이트하고 next_status로 상태 전이
    """
    stmt = (
        update(Order)
        .where(Order.id == order_id, Order.status == ORDER_STATUS.PROCESSING.value)
        .values(
            rt_cd=rt_cd,
            msg_cd=msg_cd,
            msg1=msg1,
            broker_org_no=broker_org_no,
            broker_order_no=broker_order_no,
            submitted_at=submitted_at,
            submit_response_payload=submit_response_payload,
            status=next_status.value,
            updated_at=func.now(),
        )
    )
    result = await db.execute(stmt)
    return result.rowcount > 0    