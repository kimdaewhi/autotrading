from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.db.models.order import Order

async def create_order(db: AsyncSession, order_data: dict) -> Order:
    new_order = Order(**order_data)
    
    db.add(new_order)
    await db.flush()  # 새로 생성된 객체의 ID를 가져오기 위해 flush() 호출
    await db.refresh(new_order)  # 새로 생성된 객체의 상태를 최신으로 유지하기 위해 refresh() 호출
    
    return new_order