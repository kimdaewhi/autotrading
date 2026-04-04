from pydantic_settings import BaseSettings
from urllib.parse import quote_plus

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Auto Trading System"
    APP_ENV: str = "local"  # local, development, production
    
    # Trading
    TRADING_ENV: str = "paper"  # paper or live
    
    # KIS API
    KIS_APP_KEY: str
    KIS_APP_SECRET: str
    KIS_AUTH_USER: str
    KIS_AUTH_PASSWORD: str
    
    # KIS 계좌번호(모의투자/실전투자 모두 가능)
    KIS_ACCOUNT_NO: str
    KIS_ACCOUNT_PRODUCT_CODE: str

    # Database
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    """
    TODO: DB_URL은 최초에는 Connection String을 이것으로 사용하려 했지만 
    보안상 DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME을 별도로 관리하는 것이 좋을것 같아서 안쓰게됨. 
    추후에 DB_URL은 제거하는 방향으로 리팩토링 필요. 
    또한 HOST, PORT, NAME, USER, PASSWORD도 암호화 처리 필요.
    """
    DB_URL: str
    
    # KIS REST API endpoints
    KIS_PAPER_BASE_URL: str = "https://openapivts.koreainvestment.com:29443"
    KIS_LIVE_BASE_URL: str = "https://openapi.koreainvestment.com:9443"
    
    # KIS WebSocket API endpoints
    KIS_PAPER_WS_URL: str = "ws://ops.koreainvestment.com:31000"
    KIS_LIVE_WS_URL: str = "ws://ops.koreainvestment.com:21000"
    
    # Redis
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    
    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }
    
    @property
    def kis_base_url(self) -> str:
        return self.KIS_PAPER_BASE_URL if self.TRADING_ENV == "paper" else self.KIS_LIVE_BASE_URL
    
    @property
    def kis_ws_url(self) -> str:
        return self.KIS_PAPER_WS_URL if self.TRADING_ENV == "paper" else self.KIS_LIVE_WS_URL
    
    @property
    def postgres_dsn(self) -> str:
        """
        PostgreSQL connection string (DSN) 생성.
        형식: postgresql+asyncpg://user:password@host:port/dbname
        TODO: 사용자명, DB명, 패스워드는 암호화 처리 필요
        """

        user = quote_plus(self.DB_USER or "")
        password = quote_plus(self.DB_PASSWORD or "")
        host = self.DB_HOST or "localhost"
        port = str(self.DB_PORT) if self.DB_PORT is not None else "5432"
        dbname = self.DB_NAME or ""

        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"


settings = Settings()