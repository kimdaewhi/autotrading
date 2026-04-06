import FinanceDataReader as fdr
import pandas as pd

from .base_provider import BaseMarketDataProvider


class FDRMarketDataProvider(BaseMarketDataProvider):
    
    # ⚙️ 종목 리스트 조회(한국거래소 상장 종목) - 원본 데이터프레임 반환
    def get_stock_list_raw(self) -> pd.DataFrame:
        return fdr.StockListing('KRX')
    
    
    # ⚙️ 종목 리스트 조회(한국거래소 상장 종목)
    def get_stock_list(self) -> pd.DataFrame:
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name', 'Market']].rename(columns={
            'Code': 'code',
            'Name': 'name',
            'Market': 'market'
        })
    
    
    # ⚙️ 시장 데이터 조회(Open, High, Low, Close, Volume)
    def get_ohlcv(self, code: str, start: str, end: str) -> pd.DataFrame:
        df = fdr.DataReader(code, start, end)
        return df.reset_index()