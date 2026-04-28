from pydantic_settings import BaseSettings


class StrategySettings(BaseSettings):
    
    # ── F-Score + Momentum (Core 전략) ──
    PM_FSCORE_THRESHOLD: int
    PM_MIN_MARCAP: float
    PM_MAX_MARCAP: float
    PM_UNIVERSE_N: int
    PM_LOOKBACK_DAYS: int
    PM_TOP_N: int
    PM_ABS_THRESHOLD: float
    
    # ── Reversal + Volume (Satellite 전략) ──
    # 1단계: Liquidity Filter
    RV_MIN_MARCAP: float
    RV_MAX_MARCAP: float
    RV_AVG_AMOUNT_DAYS: int
    RV_TOP_N_LIQUID: int
    
    # 2단계: Reversal Screen
    RV_REVERSAL_DAYS: int
    RV_REVERSAL_PCT: float
    
    # 3단계: Volume Spike
    RV_VOLUME_AVG_DAYS: int
    RV_VOLUME_SPIKE_RATIO: float
    
    # 4단계: Risk Cut
    RV_MAX_DRAWDOWN_PCT: float
    
    # 청산 규칙
    RV_TAKE_PROFIT_PCT: float
    RV_STOP_LOSS_PCT: float
    RV_MAX_HOLDING_DAYS: int
    
    # 포트폴리오
    RV_MAX_POSITIONS: int
    
    # 시장 필터 조건
    RV_MARKET_FILTER_ENABLED: bool
    RV_MARKET_MA_DAYS: int
    
    # 재진입 쿨다운
    RV_COOLDOWN_DAYS: int

    model_config = {
        "env_file": ".env.strategy",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

strategy_settings = StrategySettings()