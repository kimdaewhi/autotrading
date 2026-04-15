import json
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.screener.fscore import FScore
from app.strategy.filter.valuation_filter import ValuationFilter
from app.strategy.signals.momentum import MomentumStrategy
from app.strategy.backtest.services import run_backtest

provider = FDRMarketDataProvider()
momentum = MomentumStrategy(lookback_days=120, top_n=5, abs_threshold=0.0)

# 스크리너/필터 결과에서 나온 종목코드 리스트
fscore_screener = FScore(n=50)
valuation_filter = ValuationFilter(top_n=5, metric="pbr")

# =========================================================
# TODO(P3/백테스트): as_of_date 기반 백테스트 날짜 자동 결정 모듈화. 현재 annual만 사용 중, 분기보고서 fallback/lag 계산/거래일 보정 필요
#
# 현재는 year 기준으로 수동 설정하고 있지만,
# 실제로는 "특정 시점(as_of_date)에 시장에서 사용 가능했던 최신 재무데이터"를 기준으로
# 자동으로 보고서 선택 및 백테스트 시작일을 계산해야 함
#
# 필요 로직:
# 1. as_of_date 기준으로 사용 가능한 최신 보고서 선택
#    - 우선순위: 사업보고서 > 3Q > 반기 > 1Q
#    - ex) 2026-02 → 2025 사업보고서 없음 → 2024 사업보고서 or 2025 3Q fallback
#
# 2. 선택된 보고서의 실제 반영 가능 시점 계산
#    - report_release_date + lag (ex. 3~7일)
#
# 3. 거래일 기준으로 보정
#    - 주말/공휴일 → 다음 거래일로 이동
#
# 4. 최종 백테스트 구간 생성
#    - start = effective_date
#    - end = start + holding_period (ex. 12개월)
#
# 👉 핵심:
# "year" 기준이 아니라 "as_of_date 기준으로 실제 시장에 존재했던 정보"를 사용해야 함
# =========================================================

# 최종 결산보고서 기준으로 스크리닝 후 수행
year = 2024
fscore_stock_list = fscore_screener.screen(year)
stock_df = valuation_filter.filter(fscore_stock_list)

# 백테스트에 사용할 종목코드 리스트만 추출
stock_codes = stock_df["code"].astype(str).tolist()

res = run_backtest(
    provider=provider,
    strategy=momentum,
    stock_codes=stock_codes,
    benchmark_code="KS11",
    
    # ⚠️ 현재 설정은 lookahead bias 발생 가능
    # year=2025 기준이라면 실제로는 2026-04-01 이후가 맞음
    start="2024-04-01",
    end="2025-12-31",
    
    initial_cash=10_000_000,
    rebalance_interval="M",
)

print(json.dumps(res["metrics"].model_dump(), indent=2, ensure_ascii=False))