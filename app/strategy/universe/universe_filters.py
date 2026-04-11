"""
유니버스 프리셋 필터 모듈

⭐ 역할
    - 1차 스크리닝(F-Score 등)에 사용할 종목 풀(유니버스)을 구성하는 빌더 함수 모음
    - 각 빌더는 DataFrame(필수 컬럼: Code, Name, Market, Marcap)을 반환
    - Screener에서 UniverseBuilder(Callable[[], pd.DataFrame])로 주입받아 사용

⭐ 공통 필터
    - apply_base_filters() : 특수종목, 우선주, ETF/ETN 제외 등 공통 필터링
    - 빌더가 아닌 screen() 단계에서 적용 (빌더는 종목 풀 구성만 담당)
    
⚠️ Look-Ahead Bias 주의
    - 현재 모든 빌더는 FDR StockListing('KRX')의 *현재 시점* 데이터를 사용
    - 과거 시점 백테스트 시 미래 정보가 유입될 수 있음 (ex. 2026년 시총 기준으로 2023년 유니버스 구성)
    - TODO: 특정 시점 기준 시총 역산 빌더 구현 (OHLCV Close × Stocks로 과거 시총 계산)
"""
import pandas as pd
from app.market.provider.fdr_provider import FDRMarketDataProvider


# 필수 컬럼 정의 (모든 빌더가 이 컬럼을 반환해야 함)
REQUIRED_COLUMNS = ["Code", "Name", "Market", "Marcap"]



# ⚙️ 유니버스 DataFrame 검증 함수
def _validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"유니버스 DataFrame 필수 컬럼 누락: {missing}")
    return df


# ⚙️ 공통 기본 필터 (특수종목, 우선주, ETF/ETN 제외)
def apply_base_filters(
    df: pd.DataFrame,
    exclude_preferred: bool = True,
    markets: list[str] | None = None,
) -> pd.DataFrame:
    """
    exclude_preferred : 우선주 제외 여부 (기본 True)
    markets : 허용할 시장 목록 (기본 ["KOSPI", "KOSDAQ"])
    """
    if markets is None:
        markets = ["KOSPI", "KOSDAQ"]
    
    # 종목코드 숫자 6자리만 (특수종목 제외)
    df = df[df["Code"].str.match(r"^\d{6}$")]
    
    # 우선주 제외
    if exclude_preferred:
        df = df[df["Code"].str[-1] == "0"]
    
    # 시장 필터
    df = df[df["Market"].isin(markets)]
    
    return df


# ⚙️ 시가총액 상위 N개
def top_by_marcap(n: int = 200) -> pd.DataFrame:
    fdr = FDRMarketDataProvider()
    df = fdr.get_top_stock_list(n, sort_by="Marcap", ascending=False)
    
    return _validate(df[REQUIRED_COLUMNS])


# ⚙️ 시총 범위 필터 (대형주/중형주/소형주 구분)
def marcap_range(min_cap: int = 0, max_cap: int | None = None, n: int = 50, as_of_date: str = None) -> pd.DataFrame:
    """
    min_cap: 시가총액 최소값
    max_cap: 시가총액 최대값 (None이면 상한 없음)
    as_of_date: 특정 시점 기준 날짜 (YYYY-MM-DD), None이면 현재 시점
    """
    fdr = FDRMarketDataProvider()
    df = fdr.get_stock_list_raw(as_of_date=as_of_date)
    df = df[df["Marcap"] >= min_cap]
    
    if max_cap:
        df = df[df["Marcap"] <= max_cap]
    df = df.sort_values("Marcap", ascending=False).head(n)
    
    return _validate(df[REQUIRED_COLUMNS])


# ⚙️ 거래량 상위 N개
def top_by_amount(n: int = 200) -> pd.DataFrame:
    fdr = FDRMarketDataProvider()
    df = fdr.get_top_stock_list(n, sort_by="Amount", ascending=False)
    
    return _validate(df[REQUIRED_COLUMNS])


# ⚙️ 시장 구분 필터
def market_only(market: str, n: int = 300) -> pd.DataFrame:
    fdr = FDRMarketDataProvider()
    df = fdr.get_top_stock_list(n, sort_by="Marcap", ascending=False)
    df = df[df["Market"] == market]
    
    return _validate(df[REQUIRED_COLUMNS])



# ⚙️ 변동률 기반 필터 (최근 상승/하락 종목)
def by_change_ratio(n: int = 200, ascending: bool = False) -> pd.DataFrame:
    """등락률 기준 정렬 (ascending=True면 하락 상위)"""
    fdr = FDRMarketDataProvider()
    df = fdr.get_stock_list_raw()
    # NOTE: 원본 컬럼명이 오타같음... -_-;; 혹여나 나중에 수정되면 변경할 것
    df = df.sort_values("ChagesRatio", ascending=ascending)
    
    return _validate(df.head(n)[REQUIRED_COLUMNS])


# ⚙️ 복합 조건 필터
def composite(
    market: str | None = None,
    min_marcap: int = 0,
    sort_by: str = "Marcap",
    ascending: bool = False,
    n: int = 200,
) -> pd.DataFrame:
    """여러 조건을 조합하는 범용 빌더"""
    fdr = FDRMarketDataProvider()
    df = fdr.get_stock_list_raw()
    
    if market:
        df = df[df["Market"] == market]
    df = df[df["Marcap"] >= min_marcap]
    df = df.sort_values(sort_by, ascending=ascending)
    
    return _validate(df.head(n)[REQUIRED_COLUMNS])