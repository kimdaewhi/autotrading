import FinanceDataReader as fdr
import pandas as pd

from app.market.provider.base_provider import BaseMarketDataProvider


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
    
    
    # ⚙️ 상위 N개 종목 조회
    def get_top_stock_list(self, n: int, sort_by: str = "Marcap", ascending: bool = False) -> pd.DataFrame:
        df = fdr.StockListing('KRX')
        
        if sort_by not in df.columns:
            raise ValueError(f"Invalid sort_by column: {sort_by}. Available columns: {df.columns.tolist()}")
        
        sorted_df = df.sort_values(by=sort_by, ascending=ascending)
        
        return sorted_df
    
    
    # ⚙️ 시장 데이터 조회(Open, High, Low, Close, Volume)
    def get_ohlcv(self, code: str, start: str, end: str) -> pd.DataFrame:
        df = fdr.DataReader(code, start, end)
        return df.reset_index()