from datetime import date

from pydantic import BaseModel


class Period(BaseModel):
    """운용 기간(Period)"""
    start: date | None = None            # 최초 스냅샷 기준일
    end: date | None = None              # 마지막 거래일
    days: int = 0                        # 달력일 (연율화 분모)
    trading_days: int = 0                # 거래일 수 (equity 포인트 수)
    rebalance_count: int = 0             # 리밸런싱 실행 횟수


class ReturnMetrics(BaseModel):
    """수익 지표(Return Metrics)"""
    total_return: float | None = None            # 전략 전체 수익률 (%)
    period_profit: float | None = None           # 기간 손익 금액 (원). total_return 의 금액 표현
    cagr: float | None = None                    # 연환산 수익률 (%). 기간 부족 시 None

    # 벤치마크 — benchmark_return(KOSPI)이 alpha 산출 기준
    benchmark_return: float | None = None        # KOSPI 기간 수익률 (%)
    benchmark_kosdaq_return: float | None = None # KOSDAQ 기간 수익률 (%). 비교 표시용

    alpha_vs_benchmark: float | None = None      # 연율 알파 (%). 기간 부족 시 None
    excess_return: float | None = None           # total_return - benchmark_return (%p)


class RiskMetrics(BaseModel):
    """위험 지표(Risk Metrics)"""
    max_drawdown: float | None = None            # 최대 낙폭
    mdd_max_days: int | None = None              # 최대 낙폭 지속일 (고점 → 회복)
    mdd_current_days: int | None = None          # 미회복 경과일 (회복 상태면 0)
    is_recovered: bool | None = None             # 마지막 낙폭 회복 여부
    volatility: float | None = None              # 변동성 (연환산, 표본 부족 시 None)
    sharpe_ratio: float | None = None            # 샤프 비율 (표본 부족 시 None)


class RebalanceTradeMetrics(BaseModel):
    """리밸런싱 전략 지표(Rebalance Trade Metrics)"""
    period_count: int = 0                        # 수익률 산출 대상 구간 수
    win_rate: float | None = None                # 승률 (수익 구간 비율)
    avg_win: float | None = None                 # 평균 수익 구간 수익률
    avg_loss: float | None = None                # 평균 손실 구간 수익률
    profit_factor: float | None = None           # 총 이익 / 총 손실 (손실 0건이면 None)


class TurnoverMetrics(BaseModel):
    """회전율 지표(Turnover Metrics)"""
    turnover_rate: float | None = None           # 회전율 (연율 환산, 리밸런스 2회 미만이면 None)
    total_buy_value: float = 0.0                 # 총 매수 체결금액
    total_sell_value: float = 0.0                # 총 매도 체결금액
    avg_nav: float | None = None                 # 평균 순자산 (회전율 분모)



class NavPoint(BaseModel):
    """ 일별 NAV 추이(NAV Time Series) """
    date: date              # 거래일
    nav: float              # 그날의 계좌 총액
    benchmark: float | None = None   # 그날의 KOSPI 지수

class PerformanceRead(BaseModel):
    """전략 성과 지표(Performance Metrics)"""
    period: Period                        # 운용 기간
    returns: ReturnMetrics                # 수익 지표
    risk: RiskMetrics                     # 위험 지표
    trading: RebalanceTradeMetrics        # 리밸런싱 전략 지표
    turnover: TurnoverMetrics             # 회전율 지표
    nav_series: list[NavPoint] = []       # 일별 NAV 추이

    @classmethod
    def empty(cls) -> "PerformanceRead":
        """스냅샷이 없거나 데이터 포인트가 부족할 때의 빈 응답."""
        return cls(
            period=Period(),
            returns=ReturnMetrics(),
            risk=RiskMetrics(),
            trading=RebalanceTradeMetrics(),
            turnover=TurnoverMetrics(),
            nav_series=[]
        )