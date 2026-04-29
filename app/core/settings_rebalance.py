from pydantic_settings import BaseSettings


class RebalanceSettings(BaseSettings):
    
    # 리밸런싱 시작 시간
    REBALANCE_START_HOUR: int
    REBALANCE_START_MINUTE: int
    
    # 리밸런싱 종료 시간 (exclusive)
    REBALANCE_END_HOUR: int
    REBALANCE_END_MINUTE: int
    
    
    model_config = {
        "env_file": ".env.rebalance",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

rebalance_settings = RebalanceSettings()