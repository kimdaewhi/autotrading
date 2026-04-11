from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):

    @abstractmethod
    def generate_signal(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        복수 종목의 OHLCV 데이터 기반으로 시그널 생성

        Args:
            data: {종목코드: OHLCV DataFrame} 딕셔너리

        Returns:
            pd.DataFrame:
                - index: 종목코드
                - columns: signal(BUY/SELL/HOLD), 기타 전략별 부가정보
        """
        pass