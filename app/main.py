import redis.asyncio as redis
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from typing import AsyncGenerator
from sqlalchemy import text

from app.broker.kis.kis_auth import KISAuth
from app.core.settings import settings
from app.core.exceptions import KISError
from app.services.auth_service import AuthService
from app.utils.logger import get_logger
from app.db.session import get_async_engine
from app.api.router import router

from app.websocket.order_ws import router as order_ws_router


logger = get_logger(__name__)

# DB 연결 확인 함수
async def check_db_connection() -> None:
    async with get_async_engine().begin() as conn:
        await conn.execute(text("SELECT 1"))


# KIS access token 선발급 함수
async def preload_kis_access_token() -> None:
    """
    앱 시작 시 KIS access token 선발급 시도.
    실패해도 App 기동은 진행하되 로그에 경고 남김.
    """
    redis_client = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
    try:
        auth_service = AuthService(
            auth_broker=KISAuth(
                appkey=settings.KIS_APP_KEY,
                appsecret=settings.KIS_APP_SECRET,
                url=settings.kis_base_url,
            ),
            redis_client=redis_client,
        )
        access_token = await auth_service.get_valid_access_token()
        logger.info(f"KIS access token preload 완료. token_prefix={access_token[:10]}...")
    except Exception as e:
        logger.warning(f"KIS access token preload 실패. 앱 기동은 계속 진행합니다.")
    finally:
        await redis_client.close()



# FastAPI의 lifespan 이벤트를 사용하여 애플리케이션 시작 시 DB 연결 확인 및 종료 시 DB 연결 종료 처리
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DB 연결 확인 시작")
    await check_db_connection()
    logger.info("DB 연결 성공")
    
    # 1. App 시작 시 Token 선발급 시도
    await preload_kis_access_token()
    
    yield
    await get_async_engine().dispose()
    logger.info("DB 연결 종료")



# FastAPI 애플리케이션 인스턴스 생성
app = FastAPI(
    title="Auto Trading System",
    version="0.1.0",
    lifespan=lifespan,
)


# KIS 관련 예외 처리 핸들러
@app.exception_handler(KISError)
async def kis_exception_handler(request: Request, exc: KISError):
    logger.warning(f"KIS 예외 | path={request.url.path} | status={exc.status_code} | code={exc.error_code} | message={exc.message}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
        },
    )


# 루트 엔드포인트(확인용)
@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "👋🏻 Auto Trading System is running!"}

# Health Check 엔드포인트
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# API 라우터 등록
app.include_router(router=router)

# WebSocket 라우터 등록
app.include_router(order_ws_router)