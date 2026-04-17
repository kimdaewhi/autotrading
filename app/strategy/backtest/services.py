import pandas as pd
from pandas.tseries.offsets import BDay
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.backtest.runner import BacktestRunner
from app.strategy.backtest.metrics import calculate_metrics


def run_backtest(
    provider: FDRMarketDataProvider,
    strategy,
    stock_codes: list[str],
    benchmark_code: str,
    start: str,
    end: str,
    initial_cash: float = 10_000_000,
    rebalance_interval: str = "M",
    warmup_days: int = 0,
) -> dict:
    """
    포트폴리오 백테스트 전체 실행 (데이터 → 전략 → 결과 → 지표)
    
    warmup_days :   전략에 필요한 사전 데이터 기간 (ex. 모멘텀 lookback_days)
                    시작일 이전 데이터를 미리 로딩하여 초기 빈 구간 방지
    """
    
    # warmup 기간을 포함한 데이터 로딩 시작일
    data_start = pd.to_datetime(start) - BDay(warmup_days)
    data_start_str = data_start.strftime("%Y-%m-%d")
    
    # 1. 다중 종목 데이터 로드 (warmup 포함)
    data = {}
    for code in stock_codes:
        df = provider.get_ohlcv(code, data_start_str, end)
        if df.empty:
            continue
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        data[code] = df
    # 2. 벤치마크 데이터 (실제 백테스트 기간만)
    benchmark_df = provider.get_ohlcv(benchmark_code, start, end)
    benchmark_df["Date"] = pd.to_datetime(benchmark_df["Date"])
    benchmark_df.set_index("Date", inplace=True)
    
    # 3. 실행
    runner = BacktestRunner(strategy, initial_cash, rebalance_interval)
    result = runner.run(data)
    
    # 3-1. warmup 구간 제거 (실제 백테스트 기간만 남김)
    actual_start = pd.to_datetime(start)
    result = result[result.index >= actual_start]
    
    # 4. 벤치마크 지표 계산
    benchmark_return = float(
        (benchmark_df["Close"].iloc[-1] / benchmark_df["Close"].iloc[0]) - 1
    )
    
    # 5. 백테스트 지표
    metrics = calculate_metrics(
        result,
        benchmark_return=benchmark_return,
    )
    
    return {
        "result": result,
        "metrics": metrics,
        "benchmark_df": benchmark_df,
    }