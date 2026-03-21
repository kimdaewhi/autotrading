from app.core.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typing import AsyncGenerator

# 데이터베이스 연결을 위한 SQLAlchemy 비동기 엔진 생성
engine = create_async_engine(
    settings.postgres_dsn,
    echo=False,
    pool_pre_ping=True,
)

# 세션 메이커 생성
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# DB 세션 생성 및 반환하는 의존성 함수
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session