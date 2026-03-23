from fastapi import APIRouter

from app.api import router_account, router_order

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