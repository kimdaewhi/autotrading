import json
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
    
    REBALANCE:    stock_codes 필수. 스크리닝 완료된 종목 리스트를 받아 리밸런싱 시뮬레이션.
    DIRECT_TRADE: stock_codes 불필요. strategy.build_universe()로 유니버스를 구성하고
                  OHLCV를 사전 로딩한 뒤, 매일 scan_from_data()로 시뮬레이션.
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
        
        # 벤치마크 데이터도 포함 (거래일 기준용)
        bench_df = provider.get_ohlcv(benchmark_code, start, end)
        bench_df["Date"] = pd.to_datetime(bench_df["Date"])
        bench_df.set_index("Date", inplace=True)
        
        data = {"__benchmark__": bench_df, **preloaded_data}
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
    
    # ── 5. 메트릭스 계산 ──
    # DIRECT_TRADE: trade_records 기반 스윙 메트릭스
    # REBALANCE: 리밸런싱 구간 기반 메트릭스
    swing_trade_records = None
    if strategy_type == StrategyType.DIRECT_TRADE and hasattr(executor, "trade_records"):
        swing_trade_records = executor.trade_records
    
    metrics = calculate_metrics(
        result,
        benchmark_return=benchmark_return,
        trade_records=swing_trade_records,
    )
    
    # ── 6. 결과 반환 ──
    output = {
        "result": result,
        "metrics": metrics,
        "benchmark_df": benchmark_df,
    }
    
    if swing_trade_records is not None:
        output["trade_records"] = swing_trade_records
    
    return output


# ⚙️ OHLCV 데이터 로딩 헬퍼
def _load_ohlcv_data(
    provider: FDRMarketDataProvider,
    stock_codes: list[str],
    start: str,
    end: str,
    warmup_days: int = 0,
) -> dict[str, pd.DataFrame]:
    data_start = pd.to_datetime(start) - BDay(warmup_days)
    data_start_str = data_start.strftime("%Y-%m-%d")
    
    data = {}
    for code in stock_codes:
        df = provider.get_ohlcv(code, data_start_str, end)
        if df.empty:
            continue
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        data[code] = df
    
    return data