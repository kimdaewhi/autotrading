from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.exceptions import KISAuthError, KISOrderError
from app.utils.logger import get_logger
from app.api.router import router
from app.core.settings import settings


logger = get_logger(__name__)

engine = create_async_engine(
    settings.DB_URL,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def check_db_connection() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DB 연결 확인 시작")
    await check_db_connection()
    logger.info("DB 연결 성공")
    yield
    await engine.dispose()
    logger.info("DB 연결 종료")



app = FastAPI(
    title="Auto Trading System",
    version="0.1.0",
    lifespan=lifespan,
)

@app.exception_handler(KISAuthError)
async def kis_auth_exception_handler(request: Request, exc: KISAuthError):
    logger.warning(f"토큰 발급 예외 처리 | path={request.url.path} | status={exc.status_code} | code={exc.error_code} | message={exc.message}")

    return JSONResponse(
        status_code=429 if exc.error_code == "EGW00133" else 502,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
        },
    )

@app.exception_handler(KISOrderError)
async def kis_order_exception_handler(request: Request, exc: KISOrderError):
    logger.warning(f"주문 예외 처리 | path={request.url.path} | status={exc.status_code} | code={exc.error_code} | message={exc.message}")
    
    return JSONResponse(
        status_code=exc.status_code or 400,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
        },
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "👋🏻 Auto Trading System is running!"}

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router=router)