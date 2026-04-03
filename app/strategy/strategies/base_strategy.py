from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        """
        OHLCV 데이터 기반으로 시그널 생성

        return:
            pd.Series (index = 날짜)
            값: "BUY", "SELL", "HOLD"
        """
        pass