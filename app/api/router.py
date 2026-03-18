from fastapi import APIRouter

from app.api import router_auth, router_account

router = APIRouter()

router.include_router(
    router=router_auth.router,
    prefix="/auth",
    tags=["auth"],
)

router.include_router(
    router=router_account.router,
    prefix="/account",
    tags=["account"],
)