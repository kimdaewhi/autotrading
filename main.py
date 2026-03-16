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


if __name__ == "__main__":
    # 실행 : poetry run python main.py
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)