from app.core.settings import settings
from app.db.session import dispose_async_engine

# DB_URL만 localhost로 오버라이드
settings.DB_URL = "postgresql+asyncpg://postgres:1q2w3e4r!!@localhost:5432/postgres"
settings.DB_HOST = "localhost"

# Redis
settings.REDIS_HOST = "localhost"
settings.CELERY_BROKER_URL = "redis://localhost:6379/0"
settings.CELERY_RESULT_BACKEND = "redis://localhost:6379/1"


import asyncio
try:
    asyncio.get_event_loop().run_until_complete(dispose_async_engine())
except:
    pass