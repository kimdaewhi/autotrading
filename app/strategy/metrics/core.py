"""
성과 지표 계산 코어 (순수 함수)

이 모듈은 pandas / numpy 외 어떤 것도 import 하지 않는다.
DB, FDR, 백테스트 엔진, 앱 설정 어느 것도 알지 못한다.

⭐ 입력은 항상 아래 3종으로 고정한다.
    - equity          : pd.Series (DatetimeIndex 오름차순, 값은 NAV)
    - rebalance_dates : list[date] (리밸런싱 실행일)
    - benchmark       : pd.Series (equity와 동일 형태)

반환값은 전부 raw 비율(float)이다. (-0.25 = -25%)
백분율 변환 및 반올림은 스키마 직렬화 계층의 책임.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────
# ⭐ 연율화 상수
#   - CAGR      : 달력일 기준 (365)
#   - 변동성/샤프 : 거래일 기준 (252)
#   두 기준이 다른 것은 업계 관행이며, 의도된 것이다.
#   백테스트와 실운용이 반드시 같은 값을 써야 하므로 호출부에서 고정할 것.
# ─────────────────────────────────────────────────────────────

CALENDAR_DAYS_PER_YEAR = 365            # 연율화 CAGR 계산용
TRADING_DAYS_PER_YEAR = 252             # 연율화 변동성/샤프 계산용


# ─────────────────────────────────────────────────────────────
# ⭐ 반환 구조체
#   스키마(Pydantic)를 import 하지 않기 위해 dataclass 를 쓴다.
#   app/schemas/strategy/metrics.py 변환은 어댑터/서비스 계층에서 수행.
# ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DrawdownDuration:
    max_days: int           # 최대 낙폭 지속일 (고점 → 회복)
    current_days: int       # 종료 시점 기준 미회복 경과일 (회복 상태면 0)
    is_recovered: bool      # 마지막 낙폭이 회복되었는지


@dataclass(frozen=True)
class WinMetrics:
    period_count: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float | None   # 손실 0건이면 None (0.0 아님)


@dataclass(frozen=True)
class TurnoverResult:
    turnover_rate: float
    total_buy_value: float
    total_sell_value: float
    avg_nav: float



# ─────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────
def _validate_equity(equity: pd.Series) -> None:
    """equity Series 계약 검증. 어댑터가 계약을 어기면 여기서 즉시 실패한다."""
    if not isinstance(equity, pd.Series):
        raise TypeError("equity 는 pd.Series 여야 합니다.")
    if equity.empty:
        raise ValueError("equity 가 비어 있습니다.")
    if not isinstance(equity.index, pd.DatetimeIndex):
        raise TypeError("equity.index 는 DatetimeIndex 여야 합니다.")
    if not equity.index.is_monotonic_increasing:
        raise ValueError("equity.index 는 오름차순이어야 합니다.")
    if equity.isna().any():
        raise ValueError("equity 에 결측치가 있습니다. 어댑터에서 처리하세요.")
    if (equity <= 0).any():
        raise ValueError("equity 에 0 이하 값이 있습니다.")


def _daily_returns(equity: pd.Series) -> pd.Series:
    """일간 수익률. 입출금 보정은 어댑터 책임이며 여기서는 다루지 않는다."""
    return equity.pct_change().dropna()


# ─────────────────────────────────────────────────────────────
# 수익률 지표
# ─────────────────────────────────────────────────────────────
def calc_total_return(equity: pd.Series, decimals: int = 2) -> float:
    """전체 기간 누적 수익률."""
    _validate_equity(equity)
    
    # % 단위로 반환 (소수점 2자리 반올림)
    raw_return = (equity.iloc[-1] / equity.iloc[0] - 1) * 100
    return round(float(raw_return), decimals)           # 전체 기간 수익률 = (최종 NAV / 초기 NAV) - 1


def calc_cagr(equity: pd.Series, days_per_year: int = CALENDAR_DAYS_PER_YEAR, decimals: int = 2) -> float:
    """연평균 복리 수익률(CAGR, %). 기간이 1일 미만이면 0 반환"""
    _validate_equity(equity)
    
    days = (equity.index[-1] - equity.index[0]).days
    if days <= 0:
        return 0.0
    
    ratio = float(equity.iloc[-1] / equity.iloc[0])
    cagr = (ratio ** (days_per_year / days) - 1) * 100
    return round(float(cagr), decimals)


def calc_alpha(equity: pd.Series, benchmark: pd.Series, days_per_year: int = CALENDAR_DAYS_PER_YEAR) -> float:
    """
    벤치마크 대비 초과 CAGR.
    
    Jensen's Alpha(베타 회귀 기반)가 아니다. MVP 단계 정의이며,
    베타/Information Ratio 로 확장할 때 이 함수를 교체한다.
    """
    strategy_cagr = calc_cagr(equity, days_per_year)
    benchmark_cagr = calc_cagr(benchmark, days_per_year)
    return float(strategy_cagr - benchmark_cagr)



# ─────────────────────────────────────────────────────────────
# 리스크 지표
# ─────────────────────────────────────────────────────────────
def calc_max_drawdown(equity: pd.Series, decimals: int = 2) -> float:
    """최대 낙폭(MDD, %). 양수 절댓값으로 반환한다. (0.25 -> 25.0)"""
    _validate_equity(equity)
    
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    mdd_pct = abs(drawdown.min()) * 100
    return round(float(mdd_pct), decimals)


def calc_drawdown_duration(equity: pd.Series) -> DrawdownDuration:
    """
    낙폭 지속 기간(고점 → 회복)을 달력일 기준으로 계산한다.
    
    - 여러 낙폭 구간 중 최장 구간을 max_days 로 반환
    - 시리즈 종료 시점까지 회복되지 않았으면 is_recovered=False,
    경과일을 current_days 에 담는다 (max_days 후보에도 포함)
    """
    _validate_equity(equity)
    
    if len(equity) < 2:
        return DrawdownDuration(max_days=0, current_days=0, is_recovered=True)
    
    running_max = equity.cummax()
    underwater = (equity < running_max).to_numpy()
    index = equity.index
    
    max_days = 0
    current_days = 0
    is_recovered = True
    
    pos = 0
    total = len(underwater)
    
    while pos < total:
        if not underwater[pos]:
            pos += 1
            continue
        
        # 낙폭 구간 시작. 직전 인덱스가 고점.
        segment_start = pos
        while pos < total and underwater[pos]:
            pos += 1
            
        peak_pos = max(segment_start - 1, 0)
        peak_date = index[peak_pos]
        
        if pos < total:
            # 회복 완료: 고점 → 회복일
            days = (index[pos] - peak_date).days
        else:
            # 미회복: 고점 → 시리즈 종료일
            days = (index[-1] - peak_date).days
            current_days = days
            is_recovered = False
        
        max_days = max(max_days, days)
    
    return DrawdownDuration(
        max_days=max_days,
        current_days=current_days,
        is_recovered=is_recovered,
    )


def calc_volatility(
    equity: pd.Series,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """연율화 변동성(일간 수익률 표준편차 × √거래일)."""
    _validate_equity(equity)
    
    returns = _daily_returns(equity)
    if len(returns) < 2:
        return 0.0
    
    return float(returns.std(ddof=1) * np.sqrt(trading_days_per_year))


def calc_sharpe_ratio(
    equity: pd.Series,
    risk_free_rate: float = 0.0,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """
    샤프 비율.
    
    risk_free_rate 는 연율 기준으로 받아 내부에서 일간으로 환산한다.
    기본값 0.0 은 '무위험수익률 미적용'을 의미하며, 정책상 명시적 선택이다.
    """
    _validate_equity(equity)
    
    returns = _daily_returns(equity)
    if len(returns) < 2:
        return 0.0
    
    std = returns.std(ddof=1)
    if std == 0:
        return 0.0
    
    daily_rf = risk_free_rate / trading_days_per_year
    excess = returns.mean() - daily_rf
    return float(excess / std * np.sqrt(trading_days_per_year))


# ─────────────────────────────────────────────────────────────
# 거래 지표 (리밸런싱 구간 기준)
#   개별 종목 매매가 아니라 '리밸런싱 구간 1개 = 거래 1건'으로 본다.
#   체결 원장 매칭(FIFO 등) 없이 equity 만으로 계산 가능한 것이 장점.
# ─────────────────────────────────────────────────────────────
def calc_rebalance_period_returns(
    equity: pd.Series,
    rebalance_dates: list[date],
) -> list[float]:
    """리밸런싱 구간별 수익률. 마지막 구간은 시리즈 종료일까지로 계산한다."""
    _validate_equity(equity)
    
    if not rebalance_dates:
        return []
    
    last_index = equity.index[-1]
    points = sorted({pd.Timestamp(d) for d in rebalance_dates})
    points = [p for p in points if p <= last_index]
    
    if not points:
        return []
    
    returns: list[float] = []
    for i, start_point in enumerate(points):
        end_point = points[i + 1] if i + 1 < len(points) else last_index
        
        start_value = equity.asof(start_point)
        end_value = equity.asof(end_point)
        
        if pd.isna(start_value) or start_value <= 0:
            continue
        returns.append(float(end_value / start_value - 1))
        
    return returns


def calc_win_metrics(period_returns: list[float], decimals: int = 2) -> WinMetrics:
    """
    승률(%), 평균 이익(%), 평균 손실(%), Profit Factor.
    
    손실 구간이 하나도 없으면 profit_factor 는 None 이다.
    0.0 을 반환하면 '손익분기점(1.0) 미달'로 오독되므로 반드시 None 을 쓴다.
    """
    if not period_returns:
        return WinMetrics(
            period_count=0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=None,
        )
        
    values = np.asarray(period_returns, dtype=float)
    wins = values[values > 0]
    losses = values[values < 0]
    
    gross_profit = float(wins.sum())
    gross_loss = float(np.abs(losses.sum()))
    
    win_rate_pct = float((values > 0).mean()) * 100
    avg_win_pct = float(wins.mean()) * 100 if wins.size else 0.0
    avg_loss_pct = float(losses.mean()) * 100 if losses.size else 0.0
    
    return WinMetrics(
        period_count=len(values),
        win_rate=round(win_rate_pct, decimals),
        avg_win=round(avg_win_pct, decimals),
        avg_loss=round(avg_loss_pct, decimals),
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
    )


# ─────────────────────────────────────────────────────────────
# 회전율
# ─────────────────────────────────────────────────────────────
def calc_turnover(
    equity: pd.Series,
    total_buy_value: float,
    total_sell_value: float,
    use_min: bool = True,
    days_per_year: int = CALENDAR_DAYS_PER_YEAR,
) -> TurnoverResult:
    """
    회전율(연율 환산).
    
    use_min=True  : min(매수, 매도) / 평균NAV  — 펀드 회계 표준.
                    자금 유입·유출을 제외하고 재배치만 잡아낸다.
    use_min=False : (매수 + 매도) / 2 / 평균NAV — 단순 매매 규모 기준.
    
    어느 정의를 쓰든 백테스트와 실운용이 반드시 동일해야 하므로
    호출부에서 고정하고 문서에 명시할 것.
    """
    _validate_equity(equity)
    
    avg_nav = float(equity.mean())
    if avg_nav <= 0:
        return TurnoverResult(0.0, total_buy_value, total_sell_value, avg_nav)
    
    if use_min:
        traded = min(total_buy_value, total_sell_value)
    else:
        traded = (total_buy_value + total_sell_value) / 2
    
    days = (equity.index[-1] - equity.index[0]).days or 1
    annualized = (traded / avg_nav) * (days_per_year / days)
    
    return TurnoverResult(
        turnover_rate=float(annualized),
        total_buy_value=float(total_buy_value),
        total_sell_value=float(total_sell_value),
        avg_nav=avg_nav,
    )


# ────────────────────────────────────────────────────────────
# NAV 시계열 조립
# ────────────────────────────────────────────────────────────
def calc_period_profit(equity: pd.Series) -> float:
    """기간 손익 금액. 시작 NAV 대비 종료 NAV 증감."""
    _validate_equity(equity)
    return float(equity.iloc[-1] - equity.iloc[0])