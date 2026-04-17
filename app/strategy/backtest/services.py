import pandas as pd
from pandas.tseries.offsets import BDay
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.backtest.backtest_executor import BacktestExecutor
from app.strategy.backtest.metrics import calculate_metrics
from app.schemas.strategy.trading import StrategyType


def run_backtest(
    provider: FDRMarketDataProvider,
    strategy,
    benchmark_code: str,
    start: str,
    end: str,
    initial_cash: float = 10_000_000,
    stock_codes: list[str] | None = None,
    rebalance_interval: str = "M",
    warmup_days: int = 0,
) -> dict:
    """
    통합 백테스트 실행 (전략 타입에 따라 자동 분기)
    
    REBALANCE:    stock_codes 필수
    DIRECT_TRADE: stock_codes 불필요, build_universe()로 자동 구성
    """
    strategy_type = strategy.strategy_type
    
    # ── 1. 데이터 로딩 ──
    if strategy_type == StrategyType.REBALANCE:
        if not stock_codes:
            raise ValueError("REBALANCE 전략은 stock_codes가 필수입니다.")
        data = _load_ohlcv_data(provider, stock_codes, start, end, warmup_days)
        
    elif strategy_type == StrategyType.DIRECT_TRADE:
        # 유니버스 구성 + OHLCV 사전 로딩 (1번만)
        df_universe, preloaded_data = strategy.build_universe(start, end)
        
        # 벤치마크 데이터 (거래일 기준용)
        bench_df = provider.get_ohlcv(benchmark_code, start, end)
        bench_df["Date"] = pd.to_datetime(bench_df["Date"])
        bench_df.set_index("Date", inplace=True)
        
        # __benchmark__: 거래일 기준, __universe__: 종목 메타정보
        data = {
            "__benchmark__": bench_df,
            "__universe__": df_universe,
            **preloaded_data,
        }
    else:
        raise ValueError(f"지원하지 않는 strategy_type: {strategy_type}")
    
    # ── 2. 벤치마크 데이터 ──
    if strategy_type == StrategyType.REBALANCE:
        benchmark_df = provider.get_ohlcv(benchmark_code, start, end)
        benchmark_df["Date"] = pd.to_datetime(benchmark_df["Date"])
        benchmark_df.set_index("Date", inplace=True)
    else:
        benchmark_df = data["__benchmark__"]
    
    # ── 3. 실행 ──
    executor = BacktestExecutor(strategy, initial_cash, rebalance_interval)
    result = executor.run(data)
    
    # ── 3-1. warmup 구간 제거 (REBALANCE용) ──
    if warmup_days > 0:
        actual_start = pd.to_datetime(start)
        result = result[result.index >= actual_start]
    
    # ── 4. 벤치마크 수익률 ──
    benchmark_return = float(
        (benchmark_df["Close"].iloc[-1] / benchmark_df["Close"].iloc[0]) - 1
    )
    
    # ── 5. 메트릭스 ──
    swing_trade_records = None
    if strategy_type == StrategyType.DIRECT_TRADE and hasattr(executor, "trade_records"):
        swing_trade_records = executor.trade_records
    
    metrics = calculate_metrics(
        result,
        benchmark_return=benchmark_return,
        trade_records=swing_trade_records,
    )
    
    # ── 6. 반환 ──
    output = {
        "result": result,
        "metrics": metrics,
        "benchmark_df": benchmark_df,
    }
    
    if swing_trade_records is not None:
        output["trade_records"] = swing_trade_records
    
    return output


# ⚙️ OHLCV 데이터 로딩 헬퍼
def _load_ohlcv_data(provider, stock_codes, start, end, warmup_days=0):
    data_start = (pd.to_datetime(start) - BDay(warmup_days)).strftime("%Y-%m-%d")
    data = {}
    for code in stock_codes:
        df = provider.get_ohlcv(code, data_start, end)
        if df.empty:
            continue
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        data[code] = df
    return data