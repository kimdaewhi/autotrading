import json
import pandas as pd
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.backtest.visualization import plot_backtest_result
from app.strategy.strategies.ma_cross import MACrossStrategy
from app.strategy.backtest.services import run_backtest

provider = FDRMarketDataProvider()
macross = MACrossStrategy(short_window=5, long_window=20)

res = run_backtest(
    provider=provider,
    strategy=macross,
    stock_code="005930",
    benchmark_code="KS11",
    start="2025-01-01",
    end="2025-12-31",
)

print(json.dumps(res["metrics"].model_dump(), indent=2, ensure_ascii=False))
result_df = res["result"]
plot_backtest_result(result_df)