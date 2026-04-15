from pydantic import BaseModel


class StrategyRunResponse(BaseModel):
    """전략 실행 API 공통 응답"""
    strategy_name: str
    strategy_type: str
    success: bool
    dry_run: bool
    error_message: str | None = None
    summary: str | None = None
    
    # 전략/Executor 유형별 부가 정보
    metadata: dict = {}