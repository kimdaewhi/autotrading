from fastapi import APIRouter

from app.api import router_account, router_order, router_order_query, router_realtime, router_safety, router_strategy

router = APIRouter()

router.include_router(
    router=router_account.router,
    prefix="/account",
    tags=["account"],
)

router.include_router(
    router=router_order.router,
    prefix="/order",
    tags=["order"],
)

router.include_router(
    router=router_order_query.router,
    prefix="/order-query",
    tags=["order-query"],
)

router.include_router(
    router=router_safety.router,
    prefix="/safety",
    tags=["safety"],
)

router.include_router(
    router=router_realtime.router,
    prefix="/realtime",
    tags=["realtime"],
)

router.include_router(
    router=router_strategy.router,
    prefix="/strategy",
    tags=["strategy"],
)