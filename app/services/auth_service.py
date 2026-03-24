from __future__ import annotations

import asyncio
import json
import redis.asyncio as redis
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

from app.broker.kis.kis_auth import KISAuth
from app.core.exceptions import KISAuthError
from app.utils.logger import get_logger


logger = get_logger(__name__)

KST = ZoneInfo("Asia/Seoul")


class AuthService:
    """
    KIS Access Token 관리 서비스

    책임:
    1. Redis에서 토큰 조회
    2. 토큰 만료/만료임박 여부 판단
    3. 필요 시 KISAuth broker를 통해 신규 발급
    4. 동시 재발급 방지를 위한 Redis lock 처리
    """

    TOKEN_CACHE_KEY = "kis:access_token"
    TOKEN_LOCK_KEY = "kis:access_token:lock"

    # 실제 만료시각보다 조금 일찍 만료로 간주
    EXPIRY_BUFFER_SECONDS = 300  # 5분
    LOCK_EXPIRE_SECONDS = 55
    LOCK_WAIT_SECONDS = 1.0
    LOCK_RETRY_COUNT = 5

    def __init__(self, auth_broker: KISAuth, redis_client: redis.Redis) -> None:
        self.auth_broker = auth_broker
        self.redis = redis_client
    
    
    # ⚙️ 유효한 access token 반환 (캐시 우선, 필요 시 재발급)
    async def get_valid_access_token(self, force_refresh: bool = False) -> str:
        """
        유효한 access token 반환
        - force_refresh = False: 캐시 우선
        - force_refresh = True: 강제 재발급 시도
        """
        if not force_refresh:
            # 먼저 캐시에 유효한 토큰이 있는지 확인
            cached = await self._get_cached_token_payload()
            if cached and not self._is_expired_or_expiring(cached):
                return str(cached["access_token"])
        
        # 동시 재발급 방지 위해 Redis 락 시도
        lock_acquired = await self.redis.set(
            self.TOKEN_LOCK_KEY,
            "1",
            ex=self.LOCK_EXPIRE_SECONDS,
            nx=True,
        )
        
        if lock_acquired:
            try:
                # 락 획득 후 다시 한번 확인
                if not force_refresh:
                    cached = await self._get_cached_token_payload()
                    if cached and not self._is_expired_or_expiring(cached):
                        return str(cached["access_token"])
                
                # KISAuth broker 통해 신규 토큰 발급
                token_response = await self.auth_broker.get_access_token()
                
                
                payload = {
                    "access_token": token_response.access_token,
                    "token_type": token_response.token_type,
                    "expires_in": token_response.expires_in,
                    "access_token_token_expired": token_response.access_token_token_expired,
                    "issued_at": self._now().isoformat(),
                }
                
                await self._save_token_payload(payload)
                logger.info("KIS access token 신규 발급 및 Redis 저장 완료. expired_at=%s", payload["access_token_token_expired"])
                return str(payload["access_token"])
            
            finally:
                await self.redis.delete(self.TOKEN_LOCK_KEY)
        
        
        # 다른 프로세스가 발급 중이면 잠깐 대기 후 캐시 재조회
        for _ in range(self.LOCK_RETRY_COUNT):
            await asyncio.sleep(self.LOCK_WAIT_SECONDS)
            cached = await self._get_cached_token_payload()
            if cached and not self._is_expired_or_expiring(cached):
                return str(cached["access_token"])
        
        raise KISAuthError(
            message="토큰 갱신 대기 후에도 유효한 access token을 확보하지 못했습니다.",
            status_code=500,
            error_code="TOKEN_REFRESH_TIMEOUT",
        )
    
    
    # ⚙️ 캐시된 토큰 무효화 (예: 인증 실패 시) - 다음 요청에서 강제 재발급 시도하도록
    async def invalidate_access_token(self) -> None:
        await self.redis.delete(self.TOKEN_CACHE_KEY)
        logger.info("KIS access token 캐시 삭제 완료")
    
    
    # ⚙️ 강제 토큰 갱신 - 다음 요청에서 캐시 무시하고 재발급 시도하도록
    async def refresh_access_token(self) -> str:
        return await self.get_valid_access_token(force_refresh=True)
    
    
    # ----------------- 내부 유틸리티 메서드 -----------------
    # ⚙️ Redis에서 Token Payload 조회 및 파싱
    async def _get_cached_token_payload(self) -> dict[str, Any] | None:
        raw = await self.redis.get(self.TOKEN_CACHE_KEY)
        if not raw:
            return None
        
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        
        try:
            payload = json.loads(raw)
            
        except json.JSONDecodeError:
            logger.warning("KIS access token 캐시 JSON 파싱 실패. 캐시 삭제")
            await self.redis.delete(self.TOKEN_CACHE_KEY)
            return None
        
        if not payload.get("access_token"):
            return None
        
        return payload
    
    
    # ⚙️ Token Payload 저장 - 만료 시간 기준으로 TTL 설정
    async def _save_token_payload(self, payload: dict[str, Any]) -> None:
        expires_at = self._parse_expired_at(payload["access_token_token_expired"])
        ttl_seconds = max(int((expires_at - self._now()).total_seconds()), 1)
        
        await self.redis.set(
            self.TOKEN_CACHE_KEY,
            json.dumps(payload, ensure_ascii=False),
            ex=ttl_seconds,
        )
    
    
    # ⚙️ 토큰이 만료되었거나 곧 만료되는지 판단 (만료 5분 전부터 만료로 간주)
    def _is_expired_or_expiring(self, payload: dict[str, Any]) -> bool:
        expired_at_raw = payload.get("access_token_token_expired")
        if not expired_at_raw:
            return True
        
        try:
            expired_at = self._parse_expired_at(str(expired_at_raw))
        except ValueError:
            return True
        
        threshold = expired_at - timedelta(seconds=self.EXPIRY_BUFFER_SECONDS)
        return self._now() >= threshold


    @staticmethod
    def _parse_expired_at(value: str) -> datetime:
        # KIS 응답 형식: "2026-03-24 15:09:07"
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(KST)