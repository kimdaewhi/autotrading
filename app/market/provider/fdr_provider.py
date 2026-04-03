import FinanceDataReader as fdr
import pandas as pd

from .base_provider import BaseMarketDataProvider


class FDRMarketDataProvider(BaseMarketDataProvider):

    def get_stock_list(self) -> pd.DataFrame:
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name', 'Market']].rename(columns={
            'Code': 'code',
            'Name': 'name',
            'Market': 'market'
        })

    def get_ohlcv(self, code: str, start: str, end: str) -> pd.DataFrame:
        df = fdr.DataReader(code, start, end)
        return df.reset_index()