from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from typing import AsyncGenerator
from sqlalchemy import text

from app.core.exceptions import KISError
from app.utils.logger import get_logger
from app.db.session import engine
from app.api.router import router
from app.core.settings import settings


logger = get_logger(__name__)

# DB 연결 확인 함수
async def check_db_connection() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))

# FastAPI의 lifespan 이벤트를 사용하여 애플리케이션 시작 시 DB 연결 확인 및 종료 시 DB 연결 종료 처리
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DB 연결 확인 시작")
    await check_db_connection()
    logger.info("DB 연결 성공")
    yield
    await engine.dispose()
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
    logger.warning(
        f"KIS 예외 | path={request.url.path} | status={exc.status_code} | code={exc.error_code} | message={exc.message}"
    )
    
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