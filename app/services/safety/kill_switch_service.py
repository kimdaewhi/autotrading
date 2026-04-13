from redis.asyncio import Redis


class KillSwitchService:
    """
    매매 파이프라인 전체 차단용 KillSwitch 서비스
    - Redis 기반 전역 상태 저장
    - True  = 차단 ON
    - False = 차단 OFF
    TODO(P2/정책): Kill Switch ON 시 진행중인 주문(PROCESSING/ACCEPTED/PARTIAL_FILLED) 일괄 취소 기능 필요
    """

    KEY = "kill_switch:trading"
    
    def __init__(self, redis: Redis):
        self.redis = redis
    
    # ⚙️ 현재 차단 상태 조회
    async def is_on(self) -> bool:
        value = await self.redis.get(self.KEY)
        
        if value is None:
            return False
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        
        return value == "1"
    
    # ⚙️ 차단 ON
    async def turn_on(self) -> None:
        await self.redis.set(self.KEY, "1")
    
    # ⚙️ 차단 OFF
    async def turn_off(self) -> None:
        await self.redis.set(self.KEY, "0")
    
    # ⚙️ 차단 상태 설정
    async def set_state(self, enabled: bool) -> None:
        await self.redis.set(self.KEY, "1" if enabled else "0")
    
    # ⚙️ 차단 상태 조회
    async def get_state(self) -> dict:
        enabled = await self.is_on()
        return {
            "enabled": enabled,
            "message": "trading is blocked" if enabled else "trading is allowed",
        }