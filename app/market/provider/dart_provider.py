from app.core.settings import settings
from app.market.provider.base_financial_provider import BaseFinancialDataProvider


class DartProvider(BaseFinancialDataProvider):
    def __init__(self, api_key=settings.DART_API_KEY):
        self.api_key = api_key
    
    def get_financial_statements(self, stock_code: str, year: int, report_type: str):
        """
        재무제표 데이터 조회 (손익계산서, 재무상태표, 현금흐름표)
        """
        pass
    