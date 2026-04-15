
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.session import get_db
from app.market.provider.dart_provider import _load_stock_name_map
from app.repository.order_repository import get_all_orders, get_orders_by_order_action, get_orders_by_status, get_orders_by_symbol
from app.schemas.kis.order import OrderRead
from app.utils.logger import get_logger


logger = get_logger(__name__)

router = APIRouter()


# ⚙️ 주문지 리스트 조회
@router.get("/domestic-stock/order-list", response_model=list[OrderRead])
async def get_order_list(db: AsyncSession = Depends(get_db)) -> list[OrderRead]:
    orders = await get_all_orders(db=db)
    name_map = _load_stock_name_map(settings.DART_API_KEY)
    
    return [
        OrderRead.model_validate(order, from_attributes=True).model_copy(
            update={"stock_name": name_map.get(order.stock_code, "")}
        )
        for order in orders
    ]


# ⚙️ 특정 종목 주문지 조회
@router.get("/domestic-stock/order-list/{stock_code}", response_model=list[OrderRead], description="특정 종목 주문지 조회")
async def get_order_list_by_stock_code(stock_code: str,db: AsyncSession = Depends(get_db)) -> list[OrderRead]:
    orders = await get_orders_by_symbol(db=db, stock_code=stock_code)
    
    return orders


# ⚙️ 특정 상태 주문지 조회
@router.get("/domestic-stock/order-list/status/{status}", response_model=list[OrderRead], description="특정 상태 주문지 조회")
async def get_order_list_by_status(status: str, db: AsyncSession = Depends(get_db)) -> list[OrderRead]:
    orders = await get_orders_by_status(db=db, status=status)
    
    return orders


# ⚙️ 특정 주문 방향 주문지 조회
@router.get("/domestic-stock/order-list/order-action/{order_action}", response_model=list[OrderRead], description="특정 주문 방향 주문지 조회")
async def get_order_list_by_order_action(order_action: str, db: AsyncSession = Depends(get_db)) -> list[OrderRead]:
    orders = await get_orders_by_order_action(db=db, order_action=order_action)
    
    return orders