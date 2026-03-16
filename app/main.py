from fastapi import FastAPI
from app.api.router import router

app = FastAPI(
    title="Auto Trading System",
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "👋🏻 Auto Trading System is running!"}

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router=router)
