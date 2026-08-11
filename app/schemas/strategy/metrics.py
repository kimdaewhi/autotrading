from pydantic import BaseModel

class Period(BaseModel):
    """운용 기간(Period)"""
    start: str
    end: str
    days: int


class ReturnMetrics(BaseModel):
    """수익 지표(Return Metrics)"""
    total_return: float          # 전략 전체 수익률
    cagr: float                  # 연환산 수익률
    benchmark_return: float      # 벤치마크 수익률
    alpha_vs_benchmark: float    # 벤치마크 대비 초과 수익


class RiskMetrics(BaseModel):
    """위험 지표(Risk Metrics)"""
    max_drawdown: float          # 최대 낙폭
    volatility: float            # 변동성 (연환산)
    sharpe_ratio: float          # 샤프 비율


class RebalanceTradeMetrics(BaseModel):
    """리밸런싱 전략 지표(Rebalance Trade Metrics)"""
    rebalance_count: int         # 리밸런싱 횟수
    win_rate: float              # 승률 (수익 구간 비율)
    avg_win: float               # 평균 수익 구간 수익률
    avg_loss: float              # 평균 손실 구간 수익률
    profit_factor: float         # 총 이익 / 총 손실
    avg_holding_count: float     # 평균 보유 종목 수


class TurnoverMetrics(BaseModel):
    """회전율 지표(Turnover Metrics)"""
    turnover_rate: float         # 회전율 (%)
    total_buy_value: float        # 총 매수 체결금액
    total_sell_value: float       # 총 매도 체결금액
    avg_nav: float                # 평균 순자산 (회전율 분모)