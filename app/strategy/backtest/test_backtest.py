import json
import pandas as pd
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.backtest.visualization import plot_backtest_result
from app.strategy.strategies.ma_cross import MACrossStrategy
from app.strategy.backtest.services import run_backtest

provider = FDRMarketDataProvider()
macross = MACrossStrategy(short_window=5, long_window=20)

# TODO: 
# 1. 종목 선정 자동화
# 2. 벤치마크 선정 자동 매핑(ex. 국내종목 → KOSPI, 해외종목 → S&P500/NASDAQ 등)
# 3. 기간 선정
# 4. 백테스트 시뮬레이션 실행 및 결과 시각화
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