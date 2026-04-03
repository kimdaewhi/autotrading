from abc import ABC, abstractmethod
import pandas as pd


class BaseMarketDataProvider(ABC):

    @abstractmethod
    def get_stock_list(self) -> pd.DataFrame:
        """
        전체 종목 리스트 조회
        columns 예시: [code, name, market]
        """
        pass

    @abstractmethod
    def get_ohlcv(self, code: str, start: str, end: str) -> pd.DataFrame:
        """
        OHLCV 데이터 조회
        """
        pass