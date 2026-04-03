import pandas as pd
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.strategies.ma_cross import MACrossStrategy
from app.strategy.backtest.services import run_backtest

provider = FDRMarketDataProvider()
macross = MACrossStrategy(short_window=5, long_window=20)

res = run_backtest(
    provider=provider,
    strategy=macross,
    code="005930",
    start="2025-01-01",
    end="2025-12-31",
)

print(res["metrics"])