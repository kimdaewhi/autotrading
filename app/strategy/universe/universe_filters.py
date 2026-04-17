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
    - marcap_range, top_by_marcap 등은 FDR StockListing('KRX')의 *현재 시점* 데이터를 사용
    - 과거 시점 백테스트 시 미래 정보가 유입될 수 있음 (ex. 2026년 시총 기준으로 2023년 유니버스 구성)
    - 백테스트에서는 marcap_range_at()을 사용하여 과거 시점 시총을 역산하여 bias를 완화
"""
import logging

import pandas as pd
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.universe.blacklist import DART_UNAVAILABLE_CODES


logger = logging.getLogger(__name__)

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
    if markets is None:
        markets = ["KOSPI", "KOSDAQ"]
    
    # 종목코드 숫자 6자리만 (특수종목 제외)
    df = df[df["Code"].str.match(r"^\d{6}$")]
    
    # 우선주 제외
    if exclude_preferred:
        df = df[df["Code"].str[-1] == "0"]
    
    # 시장 필터
    df = df[df["Market"].isin(markets)]
    
    # DART API 조회 불가 종목 제외 (금융업, 특수법인 등)
    df = df[~df["Code"].isin(DART_UNAVAILABLE_CODES)]
    
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


# ⚙️ 시총 범위 필터 (과거 시점 기준 Look-Ahead Bias 방지용, 종가 × 발행주식수로 시총 역산)
def marcap_range_at(
    min_cap: int = 0,
    max_cap: int | None = None,
    n: int = 50,
    as_of_date: str | None = None,
) -> pd.DataFrame:
    """
    특정 시점 기준 시가총액으로 유니버스 구성 (백테스트 전용)
    
    전체 KRX 상장 종목을 대상으로, as_of_date 기준 종가 × 현재 발행주식수로
    과거 시총을 역산하여 유니버스를 구성한다.
    
    ⚠️ 제약사항
        - 발행주식수는 현재 시점 값을 사용 (유상증자/감자 반영 안 됨, 오차 ±10% 내외)
        - 상장 전 종목은 OHLCV가 없으므로 자연스럽게 제외됨 → 주요 lookahead bias 해소
        - 현재 상장폐지된 종목은 StockListing에 없으므로 포함되지 않음 (survivorship bias 잔존)
    
    ⚠️ 성능
        - 전체 ~3,000 종목 OHLCV 조회 → 첫 실행 시 10~15분 소요
        - OHLCV 디스크 캐시(joblib) 덕분에 동일 as_of_date 재실행은 즉시 완료
    
    Parameters
    ----------
    min_cap : int
        시가총액 하한 (역산 시총 기준)
    max_cap : int | None
        시가총액 상한 (None이면 상한 없음)
    n : int
        최종 반환 종목 수
    as_of_date : str | None
        기준일 (YYYY-MM-DD). None이면 현재 시점 → marcap_range()로 위임
    """
    if as_of_date is None:
        return marcap_range(min_cap, max_cap, n)
    
    fdr_provider = FDRMarketDataProvider()
    
    # ── 1. 전체 KRX 종목 풀 확보 (현재 시점) ──
    df_pool = fdr_provider.get_stock_list_raw(as_of_date=None)
    total = len(df_pool)
    logger.info(f"[marcap_range_at] 전체 {total}개 종목 대상, as_of_date={as_of_date} 시총 역산 시작")
    
    # ── 2. 각 종목의 as_of_date 기준 종가 조회 ──
    # as_of_date가 휴장일일 수 있으므로 +5영업일 범위로 조회 후 첫 번째 종가 사용
    end_date = (pd.to_datetime(as_of_date) + pd.tseries.offsets.BDay(5)).strftime("%Y-%m-%d")
    
    close_prices = {}
    skipped = 0
    
    for i, code in enumerate(df_pool["Code"], 1):
        if i % 500 == 0 or i == total:
            logger.info(
                f"[marcap_range_at] OHLCV 조회 진행: {i}/{total} "
                f"({len(close_prices)} hit, {skipped} skip)"
            )
        try:
            df_ohlcv = fdr_provider.get_ohlcv(code, as_of_date, end_date)
            if not df_ohlcv.empty:
                close_prices[code] = df_ohlcv["Close"].iloc[0]
            else:
                skipped += 1
        except Exception:
            skipped += 1
            continue
    
    logger.info(
        f"[marcap_range_at] OHLCV 조회 완료: "
        f"{len(close_prices)}개 hit, {skipped}개 skip (상장 전/오류)"
    )
    
    # ── 3. 시총 역산: 과거 종가 × 현재 발행주식수 ──
    df_pool = df_pool[df_pool["Code"].isin(close_prices.keys())].copy()
    df_pool["HistoricalClose"] = df_pool["Code"].map(close_prices)
    df_pool["HistoricalMarcap"] = df_pool["HistoricalClose"] * df_pool["Stocks"]
    
    # ── 4. 시총 필터 ──
    df_filtered = df_pool[df_pool["HistoricalMarcap"] >= min_cap]
    if max_cap:
        df_filtered = df_filtered[df_filtered["HistoricalMarcap"] <= max_cap]
    
    # ── 5. 상위 n개 (역산 시총 기준 내림차순) ──
    result = df_filtered.sort_values("HistoricalMarcap", ascending=False).head(n).copy()
    
    logger.info(
        f"[marcap_range_at] 결과: 전체 {total} → OHLCV hit {len(close_prices)} "
        f"→ 시총 필터 통과 {len(df_filtered)} → 최종 {len(result)}개"
    )
    
    # ── 6. Marcap 컬럼을 역산 시총으로 교체 (screen()과 호환성 유지) ──
    result["Marcap"] = result["HistoricalMarcap"]
    
    return _validate(result[REQUIRED_COLUMNS])


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