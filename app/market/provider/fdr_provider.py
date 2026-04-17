from pathlib import Path
import FinanceDataReader as fdr
import pandas as pd
from joblib import Memory

from app.market.provider.base_provider import BaseMarketDataProvider


# ──────────────────────────────────────────────
# OHLCV 디스크 캐시 (joblib)
# ──────────────────────────────────────────────
# 프로젝트 루트 기준 .cache/ohlcv/ 에 저장
# 캐시 초기화 필요시 해당 폴더 삭제
CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "ohlcv"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
_memory = Memory(location=str(CACHE_DIR), verbose=0)

# ⚙️ OHLCV 캐싱용 모듈 레벨 함수 (self 제외하여 캐시 키 단순화)
@_memory.cache
def _cached_get_ohlcv(code: str, start: str, end: str) -> pd.DataFrame:
    """
    joblib Memory 디스크 캐싱
    - (code, start, end) 조합이 동일하면 캐시에서 반환
    - 캐시 미스 시 FDR API 호출
    """
    df = fdr.DataReader(code, start, end)
    return df.reset_index()


class FDRMarketDataProvider(BaseMarketDataProvider):
    
    # ⚙️ 종목 리스트 조회(한국거래소 상장 종목) - 원본 데이터프레임 반환
    def get_stock_list_raw(self, as_of_date: str) -> pd.DataFrame:
        if as_of_date:
            return fdr.StockListing('KRX', as_of_date)
        return fdr.StockListing('KRX')
    
    
    # ⚙️ 종목 리스트 조회(한국거래소 상장 종목)
    def get_stock_list(self, as_of_date: str = None) -> pd.DataFrame:
        if as_of_date:
            df = fdr.StockListing('KRX', as_of_date)
        else:
            df = fdr.StockListing('KRX')
        return df[['Code', 'Name', 'Market']].rename(columns={
            'Code': 'code',
            'Name': 'name',
            'Market': 'market'
        })
    
    
    # ⚙️ 상위 N개 종목 조회
    def get_top_stock_list(self, n: int, sort_by: str = "Marcap", ascending: bool = False, as_of_date: str = None) -> pd.DataFrame:
        if as_of_date:
            df = fdr.StockListing('KRX', as_of_date)
        else:
            df = fdr.StockListing('KRX')
        
        if sort_by not in df.columns:
            raise ValueError(f"Invalid sort_by column: {sort_by}. Available columns: {df.columns.tolist()}")
        
        sorted_df = df.sort_values(by=sort_by, ascending=ascending)
        
        return sorted_df.head(n)
    
    
    # ⚙️ 시장 데이터 조회(Open, High, Low, Close, Volume) - 디스크 캐시 적용
    def get_ohlcv(self, code: str, start: str, end: str) -> pd.DataFrame:
        return _cached_get_ohlcv(code, start, end)