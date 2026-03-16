from fastapi import APIRouter

from app.api import router_auth

router = APIRouter()

router.include_router(
    router=router_auth.router,
    prefix="/auth",
    tags=["auth"],
)