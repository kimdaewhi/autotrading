# base_financial_provider.py
from abc import ABC, abstractmethod
import pandas as pd


class BaseFinancialDataProvider(ABC):
    """
    재무 데이터 제공자 인터페이스
    """
    @abstractmethod
    def get_financial_statements(
        self, stock_code: str, year: int, report_type: str
    ) -> pd.DataFrame:
        """
        재무제표 데이터 조회 (손익계산서, 재무상태표, 현금흐름표)
        """
        pass