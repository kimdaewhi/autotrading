from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.strategies.ma_cross import MACrossStrategy
from app.strategy.backtest.runner import BacktestRunner
from app.strategy.backtest.metrics import calculate_metrics


# 1. 데이터
provider = FDRMarketDataProvider()
df = provider.get_ohlcv("005930", "2024-01-01", "2024-03-01")

# 2. 전략
strategy = MACrossStrategy(5, 20)

# 3. 백테스트 실행
runner = BacktestRunner(strategy, initial_cash=1_000_000)
result = runner.run(df)

# 4. 결과 확인
print(result[["Close", "signal", "equity"]].tail(20))

# 5. 성과 지표 계산
metrics = calculate_metrics(result)
print(metrics)