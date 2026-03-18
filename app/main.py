from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.exceptions import KISAuthError, KISOrderError
from app.utils.logger import get_logger
from app.api.router import router

logger = get_logger(__name__)

app = FastAPI(
    title="Auto Trading System",
    version="0.1.0",
)

@app.exception_handler(KISAuthError)
async def kis_auth_exception_handler(request: Request, exc: KISAuthError):
    logger.warning(
        f"토큰 발급 예외 처리 | path={request.url.path} | status={exc.status_code} | code={exc.error_code} | message={exc.message}"
    )

    return JSONResponse(
        status_code=429 if exc.error_code == "EGW00133" else 502,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
        },
    )

@app.exception_handler(KISOrderError)
async def kis_order_exception_handler(request: Request, exc: KISOrderError):
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