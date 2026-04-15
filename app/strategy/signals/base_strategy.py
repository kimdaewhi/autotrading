from abc import ABC, abstractmethod
import pandas as pd

from app.schemas.strategy.trading import StrategyType, StrategyResult


class BaseStrategy(ABC):
    
    @property
    @abstractmethod
    def strategy_type(self) -> StrategyType:
        """전략 유형 — Executor 라우팅에 사용"""
        ...
    
    @abstractmethod
    def generate_signal(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        복수 종목의 OHLCV 데이터 기반으로 시그널 생성 (백테스트 호환)

        Args:
            data: {종목코드: OHLCV DataFrame} 딕셔너리
        Returns:
            pd.DataFrame: index=종목코드, columns=[signal, ...]
        """
        ...
    
    @abstractmethod
    async def execute(self, **kwargs) -> StrategyResult:
        """
        전략 전체 파이프라인 실행 — 스크리닝부터 TradeIntent 생성까지.
        
        구현체가 필요한 의존성(screener, data_provider 등)은
        __init__에서 DI로 주입받고, 여기서는 런타임 파라미터만 받는다.
        
        Returns:
            StrategyResult: Executor가 처리할 TradeIntent 리스트
        """
        ...