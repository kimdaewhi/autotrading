from app.core.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typing import AsyncGenerator

# 데이터베이스 연결을 위한 SQLAlchemy 비동기 엔진 생성
# engine = create_async_engine(
#     settings.postgres_dsn,
#     echo=False,
#     pool_pre_ping=True,
# )

# # 세션 메이커 생성
# AsyncSessionLocal = async_sessionmaker(
#     bind=engine,
#     class_=AsyncSession,
#     expire_on_commit=False,
# )

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_async_engine() -> AsyncEngine:
    """
    Celery 프로세스 안에서 현재 event loop가 결정된 뒤 엔진을 지연 생성한다.
    module import 시점에 asyncpg 엔진을 만들어두면, 이후 task마다 다른 loop에서
    재사용되면서 `attached to a different loop` 오류가 발생할 수 있다.
    """
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(
            settings.postgres_dsn,
            echo=False,
            pool_pre_ping=True,
        )
        _sessionmaker = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
    return _engine


def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    
    if _sessionmaker is None:
        get_async_engine()
    if _sessionmaker is None:
        raise RuntimeError("Async sessionmaker initialization failed.")
    
    return _sessionmaker


class _AsyncSessionLocalProxy:
    """
    기존 `AsyncSessionLocal()` 호출 패턴을 유지하기 위한 프록시.
    테스트 코드 monkeypatch와 기존 async with 패턴을 깨지 않으면서
    실제 sessionmaker는 loop가 준비된 뒤 지연 생성한다.
    """
    def __call__(self, *args, **kwargs):
        return get_async_sessionmaker()(*args, **kwargs)


AsyncSessionLocal = _AsyncSessionLocalProxy()


async def dispose_async_engine() -> None:
    global _engine, _sessionmaker
    
    if _engine is not None:
        await _engine.dispose()
        
    _engine = None
    _sessionmaker = None

# DB 세션 생성 및 반환하는 의존성 함수
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session