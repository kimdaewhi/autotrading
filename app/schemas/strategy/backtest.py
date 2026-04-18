from pydantic import BaseModel

"""
백테스트 결과 집계 및 리포트 생성을 위한 스키마 정의
"""
class Period(BaseModel):
    start: str
    end: str
    days: int


class ReturnMetrics(BaseModel):
    total_return: float          # 전략 전체 수익률
    cagr: float                  # 연환산 수익률
    benchmark_return: float      # 벤치마크 수익률
    alpha_vs_benchmark: float    # 벤치마크 대비 초과 수익


class RiskMetrics(BaseModel):
    max_drawdown: float          # 최대 낙폭
    volatility: float            # 변동성 (연환산)
    sharpe_ratio: float          # 샤프 비율


# ── 포트폴리오 리밸런싱 전략용 (REBALANCE) ──
class RebalanceTradeMetrics(BaseModel):
    rebalance_count: int         # 리밸런싱 횟수
    win_rate: float              # 승률 (수익 구간 비율)
    avg_win: float               # 평균 수익 구간 수익률
    avg_loss: float              # 평균 손실 구간 수익률
    profit_factor: float         # 총 이익 / 총 손실
    avg_holding_count: float     # 평균 보유 종목 수


# ── 스윙 개별매매 전략용 (DIRECT_TRADE) ──
class SwingTradeMetrics(BaseModel):
    trade_count: int             # 총 트레이드 수
    win_rate: float              # 승률 (수익 트레이드 비율)
    avg_win: float               # 평균 수익 트레이드 수익률
    avg_loss: float              # 평균 손실 트레이드 수익률
    profit_factor: float         # 총 이익 / 총 손실
    avg_holding_days: float      # 평균 보유일
    avg_holding_count: float     # 평균 보유 종목 수
    
    # 청산 사유별 비율
    take_profit_pct: float       # 익절 비율 (%)
    stop_loss_pct: float         # 손절 비율 (%)
    time_exit_pct: float         # 시간 청산 비율 (%)


class BacktestMetrics(BaseModel):
    period: Period
    returns: ReturnMetrics
    risk: RiskMetrics
    trade: RebalanceTradeMetrics | SwingTradeMetrics