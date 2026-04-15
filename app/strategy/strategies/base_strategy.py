from abc import ABC, abstractmethod

from app.strategy.signals.base_signal import BaseSignal
from app.schemas.strategy.trading import StrategyType, StrategyResult


class BaseStrategy(BaseSignal, ABC):
    """
    완결형 전략 베이스 클래스
    
    스크리닝 → 데이터 로딩 → 시그널 생성 → TradeIntent 변환까지
    자기 완결적으로 실행하는 전략 모듈.
    
    필요한 의존성(screener, data_provider 등)은 __init__에서 DI로 주입받고,
    execute()는 런타임 파라미터만 받는다.
    """

    @property
    @abstractmethod
    def strategy_type(self) -> StrategyType:
        """전략 실행 유형 — Executor 라우팅에 사용"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> StrategyResult:
        """
        전략 전체 파이프라인 실행
        
        Returns:
            StrategyResult: Executor가 처리할 TradeIntent 리스트
        """
        ...