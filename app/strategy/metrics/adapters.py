import pandas as pd
from app.market.provider.fdr_provider import FDRMarketDataProvider



fdr = FDRMarketDataProvider()


def build_equity_series(account_no: str, start_date: str, end_date: str) -> pd.Series:
    """
    계좌별 일별 순자산(Equity) 시계열 생성
    - account_no: 계좌번호
    - start_date: 조회 시작일 (YYYY-MM-DD)
    - end_date: 조회 종료일 (YYYY-MM-DD)
    """
    # 1. 계좌별 기간 내 rebalance 스냅샷 데이터 조회
    
    # 2. 스냅샷 데이터의 전체 종목 코드 추출
    
    # 3. FDR : 종목별 일별 종가 데이터 조회 (OHLCV, start_date ~ end_date)
    
    # 4. 영업일 인덱스 생성
    
    # 5. 각 영업일 t에 대해, 스냅샷 기준 보유 종목별 평가금액 합산하여 일별 순자산 계산
    
    # 6. pd.Series로 반환 (index: 영업일, values: 일별 순자산)