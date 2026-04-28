from pydantic_settings import BaseSettings


class RebalanceSettings(BaseSettings):
    
    # 리밸런싱 스크리닝 시작 시간
    REBALANCE_SCREENING_HOUR: int
    REBALANCE_SCREENING_MINUTE: int
    
    # 리밸런싱 주문 실행 시간
    REBALANCE_EXECUTION_START_HOUR: int
    REBALANCE_EXECUTION_START_MINUTE: int
    
    # 리밸런싱 종료 시간
    REBALANCE_EXECUTION_END_HOUR: int
    REBALANCE_EXECUTION_END_MINUTE: int
    
    
    model_config = {
        "env_file": ".env.rebalance",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

rebalance_settings = RebalanceSettings()