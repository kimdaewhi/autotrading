from fastapi import FastAPI

app = FastAPI(title="Auto Trading System (Public Release)", version="0.1.0-public")


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Public release - core trading modules are removed."}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
