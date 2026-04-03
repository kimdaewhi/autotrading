import pandas as pd

from app.strategy.backtest.runner import BacktestRunner
from app.strategy.backtest.metrics import calculate_metrics


def run_backtest(
    provider,
    strategy,
    code: str,
    start: str,
    end: str,
    initial_cash: float = 1_000_000,
) -> dict:
    """
    백테스트 전체 실행 (데이터 → 전략 → 결과 → 지표)
    """

    # 1. 데이터
    df = provider.get_ohlcv(code, start, end)

    df["Date"] = pd.to_datetime(df["Date"])
    df.set_index("Date", inplace=True)

    # 2. 실행
    runner = BacktestRunner(strategy, initial_cash)
    result = runner.run(df)

    # 3. 지표
    metrics = calculate_metrics(result)

    return {
        "result": result,
        "metrics": metrics,
    }