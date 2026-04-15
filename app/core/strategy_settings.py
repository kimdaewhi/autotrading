from pydantic_settings import BaseSettings


class StrategySettings(BaseSettings):
    FSCORE_THRESHOLD: int
    MIN_MARCAP: float
    MAX_MARCAP: float
    UNIVERSE_N: int
    LOOKBACK_DAYS: int
    TOP_N: int
    ABS_THRESHOLD: float

    model_config = {
        "env_file": ".env.strategy",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

strategy_settings = StrategySettings()