import pandas as pd

from app.strategy.backtest.runner import BacktestRunner
from app.strategy.backtest.metrics import calculate_metrics


def run_backtest(
    provider,
    strategy,
    stock_code: str,
    benchmark_code: str,
    start: str,
    end: str,
    initial_cash: float = 1_000_000,
) -> dict:
    """
    백테스트 전체 실행 (데이터 → 전략 → 결과 → 지표)
    """

    # 1. 데이터
    df = provider.get_ohlcv(stock_code, start, end)
    benchmark_df = provider.get_ohlcv(benchmark_code, start, end)  # 벤치마크
    
    # 2. 날짜 컬럼 인덱싱(타깃 전략 & 벤치마크 모두; 알파 계산에 사용)
    df["Date"] = pd.to_datetime(df["Date"])
    df.set_index("Date", inplace=True)
    
    benchmark_df["Date"] = pd.to_datetime(benchmark_df["Date"])
    benchmark_df.set_index("Date", inplace=True)

    # 3. 실행
    runner = BacktestRunner(strategy, initial_cash)
    result = runner.run(df)
    
    # 4. 벤치마크 지표 계산 (기간 수익률)
    buy_hold_return = float((df["Close"].iloc[-1] / df["Close"].iloc[0]) - 1)           # 존버 수익률
    benchmark_return = float((benchmark_df["Close"].iloc[-1] / benchmark_df["Close"].iloc[0]) - 1)  # 벤치마크 수익률

    # 3. 백테스트 지표
    metrics = calculate_metrics(
        result,
        buy_hold_return=buy_hold_return,
        benchmark_return=benchmark_return
    )

    return {
        "result": result,
        "metrics": metrics,
    }