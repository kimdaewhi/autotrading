from collections.abc import AsyncGenerator
from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core.settings import settings
from app.schemas.safety.kill_switch import (
    KillSwitchStateResponse,
    KillSwitchUpdateRequest,
)
from app.services.safety.kill_switch_service import KillSwitchService



router = APIRouter()

async def get_redis() -> AsyncGenerator[Redis, None]:
    redis = Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
    try:
        yield redis
    finally:
        await redis.close()

# ⚙️ KillSwitch 상태 조회 API
@router.get("/kill-switch", response_model=KillSwitchStateResponse)
async def get_kill_switch(
    redis: Redis = Depends(get_redis),
):
    service = KillSwitchService(redis)
    state = await service.get_state()
    return KillSwitchStateResponse(**state)


# ⚙️ KillSwitch 상태 업데이트 API
@router.patch("/kill-switch", response_model=KillSwitchStateResponse)
async def update_kill_switch(
    request: KillSwitchUpdateRequest,
    redis: Redis = Depends(get_redis),
):
    service = KillSwitchService(redis)
    await service.set_state(request.enabled)
    state = await service.get_state()
    return KillSwitchStateResponse(**state)