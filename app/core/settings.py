from pydantic_settings import BaseSettings

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
    KIS_AUTH_PASSWORD_PASSWORD: str
    
    # KIS 계좌번호(모의투자/실전투자 모두 가능)
    KIS_ACCOUNT_NO: str
    KIS_ACCOUNT_PRODUCT_CODE: str

    # Database
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_URL: str
    
    # KIS endpoints
    KIS_PAPER_BASE_URL: str = "https://openapivts.koreainvestment.com:29443"
    KIS_LIVE_BASE_URL: str = "https://openapi.koreainvestment.com:9443"
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }
    
    @property
    def kis_base_url(self) -> str:
        return self.KIS_PAPER_BASE_URL if self.TRADING_ENV == "paper" else self.KIS_LIVE_BASE_URL


settings = Settings()