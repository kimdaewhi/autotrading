from fastapi import FastAPI

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