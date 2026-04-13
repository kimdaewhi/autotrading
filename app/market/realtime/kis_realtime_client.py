from __future__ import annotations

import asyncio
import json
from typing import Any

from websockets.asyncio.client import connect, ClientConnection

import redis.asyncio as redis

from app.broker.kis.enums import TRID
from app.broker.kis.kis_auth import KISAuth
from app.core.settings import settings
from app.market.realtime.base_client import BaseRealtimeClient
from app.schemas.kis.kis import RealtimeSubscribeRequest
from app.schemas.kis.realtime import KisRealtimePrice, KIS_REALTIME_PRICE_FIELDS
from app.services.kis.auth_service import AuthService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class KISRealtimeClient(BaseRealtimeClient):
    """
    한국투자증권 WebSocket 실시간 시세 클라이언트
    
    책임:
    1. 한투 WebSocket 서버에 클라이언트로 접속
    2. 종목 구독/해제 요청
    3. PINGPONG 처리 및 연결 유지
    4. 연결 끊김 시 자동 재연결
    """
    
    PINGPONG_TR_ID = "PINGPONG"
    RECONNECT_DELAY_SECONDS = 3
    MAX_RECONNECT_ATTEMPTS = 10
    
    def __init__(self) -> None:
        self._ws: ClientConnection | None = None
        self._subscribed_codes: set[str] = set()
        self._running: bool = False
        self._approval_key: str | None = None
    
    
    def _handle_realtime_data(self, raw: str) -> None:
        """
        실시간 체결 데이터 파싱
        형식: 암호화여부|TR_ID|건수|데이터(^구분)
        예: 0|H0STCNT0|003|005930^102219^...^005930^102220^...^005930^102220^...
        """
        parts = raw.split("|", 3)  # 최대 4조각: [암호화여부, TR_ID, 건수, 데이터]
        if len(parts) < 4:
            logger.warning(f"실시간 데이터 형식 오류. parts={len(parts)}")
            return
        
        encrypted = parts[0]
        tr_id = parts[1]
        count = int(parts[2])
        data_str = parts[3]
        
        if encrypted == "1":
            # TODO(P3/확장): AES256 복호화 처리 - 실전투자 암호화 데이터 대응
            logger.debug("암호화된 데이터 수신. (복호화 미구현)")
            return
        
        # ^ 구분자로 전체 분리 후, 필드 개수 단위로 잘라서 건별 파싱
        all_fields = data_str.split("^")
        field_count = len(KIS_REALTIME_PRICE_FIELDS)
        
        for i in range(count):
            start = i * field_count
            end = start + field_count
            
            if end > len(all_fields):
                logger.warning(f"실시간 데이터 필드 부족. expected={end}, actual={len(all_fields)}")
                break
            
            fields = all_fields[start:end]
            try:
                price = KisRealtimePrice.from_fields(fields)
                logger.debug(
                    f"[체결] {price.mksc_shrn_iscd} | "
                    f"{price.stck_cntg_hour} | "
                    f"{price.stck_prpr}원 | "
                    f"전일비 {price.prdy_vrss} ({price.prdy_ctrt}%) | "
                    f"체결량 {price.cntg_vol} | "
                    f"누적 {price.acml_vol}"
                )
                # TODO(P3/확장): 콜백/이벤트로 UI 또는 전략 모듈에 실시간 체결 데이터 전달 - 단기 전략 구현 시 필요
            except (IndexError, ValueError) as e:
                logger.warning(f"실시간 데이터 파싱 오류. index={i}, error={e}")
    
    # ========================= 인증 =========================
    # ⚙️ Redis에서 WebSocket 승인키(approval_key) 조회
    async def _get_approval_key(self) -> str:
        redis_client = redis.from_url(
            settings.CELERY_BROKER_URL,
            decode_responses=False,
        )
        try:
            auth_service = AuthService(
                auth_broker=KISAuth(
                    appkey=settings.KIS_APP_KEY,
                    appsecret=settings.KIS_APP_SECRET,
                    url=settings.kis_base_url,
                ),
                redis_client=redis_client,
            )
            response = await auth_service.get_websocket_key()
            return response.approval_key  # 객체에서 문자열 추출
        finally:
            await redis_client.close()

    # ========================= 연결 =========================
    # ⚙️ WebSocket 서버에 연결
    async def connect(self) -> None:
        self._approval_key = await self._get_approval_key()
        ws_url = f"{settings.kis_ws_url}/tryitout/{TRID.DOMESTIC_STOCK_REALTIME_PRICE}"
        self._ws = await connect(ws_url)
        logger.info(f"한투 WebSocket 연결 성공. url={ws_url}")
    
    # ⚙️ 연결 종료
    async def disconnect(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("한투 WebSocket 연결 종료.")
    
    
    # ========================= 구독 =========================
    # ⚙️ 종목 구독 요청 (tr_type="1" → 구독, tr_type="2" → 구독 해제)
    async def subscribe(self, stock_code: str) -> None:
        if not self._ws or not self._approval_key:
            raise RuntimeError("WebSocket이 연결되지 않았습니다.")
        
        message = self._build_subscribe_message(
            tr_type="1",
            tr_id=TRID.DOMESTIC_STOCK_REALTIME_PRICE,
            tr_key=stock_code,
        )
        await self._ws.send(message)
        self._subscribed_codes.add(stock_code)
        logger.info(f"종목 구독 요청. stock_code={stock_code}")
    
    # ⚙️ 종목 구독 해제 요청
    async def unsubscribe(self, stock_code: str) -> None:
        if not self._ws or not self._approval_key:
            raise RuntimeError("WebSocket이 연결되지 않았습니다.")
        
        message = self._build_subscribe_message(
            tr_type="2",
            tr_id=TRID.DOMESTIC_STOCK_REALTIME_PRICE,
            tr_key=stock_code,
        )
        await self._ws.send(message)
        self._subscribed_codes.discard(stock_code)
        logger.info(f"종목 구독 해제 요청. stock_code={stock_code}")
        
        
    # ========================= 메시지 처리 =========================
    # ⚙️ 수신 메시지 처리 (실시간 데이터 vs JSON 메시지 구분, PINGPONG 응답, 구독 응답 로그)
    async def on_message(self, message: Any) -> None:
        if isinstance(message, str):
            # 파이프 구분자로 시작하면 실시간 데이터
            if message[:1] in ("0", "1"):
                self._handle_realtime_data(message)
                return
            
            # JSON 메시지 처리
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning(f"알 수 없는 메시지 형식. message={message[:100]}")
                return
            
            header = data.get("header", {})
            tr_id = header.get("tr_id")
            
            # PINGPONG 처리
            if tr_id == self.PINGPONG_TR_ID:
                await self._ws.send(message)
                logger.debug("PINGPONG 응답 전송.")
                return
            
            # 구독 응답 처리
            body = data.get("body", {})
            rt_cd = body.get("rt_cd")
            if rt_cd == "0":
                msg1 = body.get("output", {}).get("msg1", "")
                logger.info(f"구독 응답 수신. tr_id={tr_id}, msg={msg1}")
            elif rt_cd == "1":
                msg1 = body.get("output", {}).get("msg1", "")
                logger.warning(f"구독 요청 실패. tr_id={tr_id}, msg={msg1}")

    # ========================= 메인 루프 =========================
    # ⚙️ WebSocket 연결 및 메시지 수신 루프 시작
    async def start(self) -> None:
        self._running = True
        reconnect_attempts = 0
        
        # 연결 유지 및 재연결 루프
        while self._running:
            try:
                await self.connect()
                reconnect_attempts = 0
                
                # 재연결 시 기존 구독 종목 복구
                if self._subscribed_codes:
                    for code in list(self._subscribed_codes):
                        await self.subscribe(code)
                    logger.info(f"구독 종목 복구 완료. count={len(self._subscribed_codes)}")
                
                # 메시지 수신 루프
                async for message in self._ws:
                    await self.on_message(message)
            
            except Exception as e:
                logger.warning(f"한투 WebSocket 연결 끊김 또는 오류. error={e}")
            finally:
                self._ws = None
            
            if not self._running:
                break
            
            # 재연결 시도
            reconnect_attempts += 1
            if reconnect_attempts > self.MAX_RECONNECT_ATTEMPTS:
                logger.error(f"최대 재연결 시도 초과. attempts={reconnect_attempts}")
                break
            
            # 재연결 대기 (지수 백오프 방식)
            delay = min(self.RECONNECT_DELAY_SECONDS * reconnect_attempts, 30)
            logger.info(f"재연결 시도. attempt={reconnect_attempts}, delay={delay}s")
            await asyncio.sleep(delay)
    
    # ========================= 내부 유틸리티 =========================
    def _build_subscribe_message(self, tr_type: str, tr_id: str, tr_key: str) -> str:
        req = RealtimeSubscribeRequest(
            header=RealtimeSubscribeRequest.Header(
                approval_key=self._approval_key,
                tr_type=tr_type,
            ),
            body=RealtimeSubscribeRequest.Body(
                input=RealtimeSubscribeRequest.Body.Input(
                    tr_id=tr_id,
                    tr_key=tr_key,
                )
            ),
        )
        return req.model_dump_json(by_alias=True)