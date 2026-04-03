from pydantic import BaseModel, Field


class Period(BaseModel):
    start: str   # 백테스트 시작일 (YYYY-MM-DD)
    end: str     # 백테스트 종료일 (YYYY-MM-DD)
    days: int    # 전체 기간 (캘린더 기준 일수)


class ReturnMetrics(BaseModel):
    total_return: float          # 전략 전체 수익률 (초기 자본 대비 최종 자산 증가율)
    cagr: float                  # 연환산 수익률 (복리 기준)
    buy_hold_return: float       # 동일 종목 단순 보유 수익률 (전략 없이 그냥 들고 있을 경우)
    benchmark_return: float      # 벤치마크 수익률 (예: 코스피)
    alpha_vs_buy_hold: float     # 종목 단순보유 대비 초과 수익 (buy & hold 대비 α)
    alpha_vs_benchmark: float    # 벤치마크 대비 초과 수익 (벤치마크 대비 α)


class RiskMetrics(BaseModel):
    max_drawdown: float          # 최대 낙폭 (고점 대비 최대 손실 비율)
    volatility: float            # 변동성 (일별 수익률 표준편차의 연환산 값)
    sharpe_ratio: float          # 샤프 비율 (수익 대비 변동성, 위험 대비 성과 지표)


class TradeMetrics(BaseModel):
    trade_count: int             # 총 거래 횟수 (BUY → SELL 완료 기준)
    win_rate: float              # 승률 (수익 거래 비율)
    avg_win: float               # 평균 수익 거래 수익률
    avg_loss: float              # 평균 손실 거래 수익률
    profit_factor: float         # 총 이익 / 총 손실 (1 이상이면 유리)
    avg_holding_bars: float      # 평균 보유 기간 (봉/영업일 기준)


class BacktestMetrics(BaseModel):
    period: Period               # 백테스트 기간 정보
    returns: ReturnMetrics       # 수익률 및 알파 지표
    risk: RiskMetrics            # 리스크 지표
    trade: TradeMetrics          # 거래 통계 지표