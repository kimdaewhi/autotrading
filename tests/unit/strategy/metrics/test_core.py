"""
성과 지표 코어 계산 단위 테스트

DB / FDR / 네트워크 의존 없음. pd.Series 를 직접 만들어 정답과 대조한다.
기대값은 전부 손으로 검산 가능한 수치로 구성했다.
"""

from datetime import date

import pandas as pd
import pytest

from app.strategy.metrics.core import (
    calc_alpha,
    calc_cagr,
    calc_drawdown_duration,
    calc_max_drawdown,
    calc_rebalance_period_returns,
    calc_sharpe_ratio,
    calc_total_return,
    calc_turnover,
    calc_volatility,
    calc_win_metrics,
)


# ─────────────────────────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────────────────────────
def _series(values: list[float], start: str = "2026-04-01") -> pd.Series:
    """연속 달력일 인덱스를 가진 equity Series 생성."""
    index = pd.date_range(start=start, periods=len(values), freq="D")
    return pd.Series([float(v) for v in values], index=index)


@pytest.fixture
def equity_with_drawdown() -> pd.Series:
    """
    04-01  100   시작
    04-02  120   고점
    04-03   90   낙폭 -25%
    04-04  120   회복
    04-05  110   재하락 (미회복 상태로 종료)
    """
    return _series([100, 120, 90, 120, 110])


@pytest.fixture
def equity_monotonic() -> pd.Series:
    """단조 증가. 낙폭 없음, 손실 구간 없음."""
    return _series([100, 110, 120, 130])


@pytest.fixture
def equity_flat() -> pd.Series:
    """변동 없음. 변동성 0."""
    return _series([100, 100, 100])


# ─────────────────────────────────────────────────────────────
# 수익률
# ─────────────────────────────────────────────────────────────
class TestReturns:
    def test_총수익률(self, equity_with_drawdown):
        # 110 / 100 - 1
        assert calc_total_return(equity_with_drawdown) == pytest.approx(0.10)

    def test_CAGR_기간이_1년이면_총수익률과_같다(self):
        equity = pd.Series(
            [100.0, 120.0],
            index=pd.to_datetime(["2026-01-01", "2027-01-01"]),  # 정확히 365일
        )
        assert calc_cagr(equity) == pytest.approx(0.20)

    def test_CAGR_수익이_없으면_0(self, equity_flat):
        assert calc_cagr(equity_flat) == pytest.approx(0.0)

    def test_알파는_벤치마크_대비_초과_CAGR(self):
        index = pd.to_datetime(["2026-01-01", "2027-01-01"])
        strategy = pd.Series([100.0, 120.0], index=index)   # +20%
        benchmark = pd.Series([100.0, 110.0], index=index)  # +10%

        assert calc_alpha(strategy, benchmark) == pytest.approx(0.10)


# ─────────────────────────────────────────────────────────────
# 리스크
# ─────────────────────────────────────────────────────────────
class TestRisk:
    def test_MDD는_음수로_반환된다(self, equity_with_drawdown):
        # 고점 120 → 저점 90
        assert calc_max_drawdown(equity_with_drawdown) == pytest.approx(-0.25)

    def test_MDD_단조증가면_0(self, equity_monotonic):
        assert calc_max_drawdown(equity_monotonic) == pytest.approx(0.0)

    def test_낙폭기간_고점에서_회복까지_달력일(self, equity_with_drawdown):
        result = calc_drawdown_duration(equity_with_drawdown)

        # 04-02 고점 → 04-04 회복 = 2일
        assert result.max_days == 2
        # 04-04 고점 → 04-05 종료, 미회복 = 1일
        assert result.current_days == 1
        assert result.is_recovered is False

    def test_낙폭기간_낙폭이_없으면_0(self, equity_monotonic):
        result = calc_drawdown_duration(equity_monotonic)

        assert result.max_days == 0
        assert result.current_days == 0
        assert result.is_recovered is True

    def test_변동성_변동이_없으면_0(self, equity_flat):
        assert calc_volatility(equity_flat) == pytest.approx(0.0)

    def test_변동성_연율화_계수가_반영된다(self, equity_with_drawdown):
        vol_252 = calc_volatility(equity_with_drawdown, trading_days_per_year=252)
        vol_63 = calc_volatility(equity_with_drawdown, trading_days_per_year=63)

        # √252 / √63 = 2
        assert vol_252 == pytest.approx(vol_63 * 2)

    def test_샤프_표준편차가_0이면_0(self, equity_flat):
        assert calc_sharpe_ratio(equity_flat) == pytest.approx(0.0)

    def test_샤프_무위험수익률이_높을수록_낮아진다(self, equity_with_drawdown):
        sharpe_zero = calc_sharpe_ratio(equity_with_drawdown, risk_free_rate=0.0)
        sharpe_high = calc_sharpe_ratio(equity_with_drawdown, risk_free_rate=0.05)

        assert sharpe_high < sharpe_zero


# ─────────────────────────────────────────────────────────────
# 거래 지표 (리밸런싱 구간 기준)
# ─────────────────────────────────────────────────────────────
class TestTradeMetrics:
    def test_구간수익률_마지막_구간은_종료일까지(self, equity_with_drawdown):
        returns = calc_rebalance_period_returns(
            equity_with_drawdown, [date(2026, 4, 1), date(2026, 4, 3)]
        )

        assert len(returns) == 2
        assert returns[0] == pytest.approx(-0.10)         # 100 → 90
        assert returns[1] == pytest.approx(0.2222222, abs=1e-6)  # 90 → 110

    def test_구간수익률_리밸런스일이_없으면_빈_리스트(self, equity_with_drawdown):
        assert calc_rebalance_period_returns(equity_with_drawdown, []) == []

    def test_승률과_손익비(self, equity_with_drawdown):
        returns = calc_rebalance_period_returns(
            equity_with_drawdown, [date(2026, 4, 1), date(2026, 4, 3)]
        )
        result = calc_win_metrics(returns)

        assert result.period_count == 2
        assert result.win_rate == pytest.approx(0.5)
        assert result.profit_factor == pytest.approx(2.2222222, abs=1e-6)

    def test_손실이_0건이면_profit_factor는_None(self, equity_monotonic):
        """
        기존 backtest/metrics.py 는 이 경우 0.0 을 반환했다.
        0.0 은 손익분기점(1.0) 미달로 오독되므로 None 이어야 한다.
        """
        returns = calc_rebalance_period_returns(
            equity_monotonic, [date(2026, 4, 1), date(2026, 4, 3)]
        )
        result = calc_win_metrics(returns)

        assert result.win_rate == pytest.approx(1.0)
        assert result.profit_factor is None

    def test_구간이_없으면_기본값(self):
        result = calc_win_metrics([])

        assert result.period_count == 0
        assert result.profit_factor is None


# ─────────────────────────────────────────────────────────────
# 회전율
# ─────────────────────────────────────────────────────────────
class TestTurnover:
    @pytest.fixture
    def equity_one_year(self) -> pd.Series:
        return pd.Series(
            [1_000_000.0, 1_000_000.0],
            index=pd.to_datetime(["2026-01-01", "2027-01-01"]),
        )

    def test_매수매도가_같으면_회전율은_비율_그대로(self, equity_one_year):
        result = calc_turnover(equity_one_year, 500_000, 500_000)

        assert result.turnover_rate == pytest.approx(0.5)
        assert result.avg_nav == pytest.approx(1_000_000)

    def test_매도가_없으면_회전율_0(self, equity_one_year):
        """min(매수, 매도) 정의에서는 매수만 있는 최초 구간의 회전율이 0이다."""
        result = calc_turnover(equity_one_year, 500_000, 0)

        assert result.turnover_rate == pytest.approx(0.0)

    def test_use_min_False면_평균_기준(self, equity_one_year):
        result = calc_turnover(equity_one_year, 500_000, 0, use_min=False)

        assert result.turnover_rate == pytest.approx(0.25)


# ─────────────────────────────────────────────────────────────
# 입력 계약 검증
# ─────────────────────────────────────────────────────────────
class TestValidation:
    def test_빈_시리즈는_예외(self):
        with pytest.raises(ValueError):
            calc_max_drawdown(pd.Series([], dtype="float64", index=pd.DatetimeIndex([])))

    def test_결측치가_있으면_예외(self):
        equity = _series([100, 110, 120])
        equity.iloc[1] = float("nan")

        with pytest.raises(ValueError):
            calc_max_drawdown(equity)

    def test_0이하_값이_있으면_예외(self):
        with pytest.raises(ValueError):
            calc_max_drawdown(_series([100, 0, 120]))

    def test_인덱스가_역순이면_예외(self):
        equity = _series([100, 110, 120]).iloc[::-1]

        with pytest.raises(ValueError):
            calc_max_drawdown(equity)

    def test_DatetimeIndex가_아니면_예외(self):
        with pytest.raises(TypeError):
            calc_max_drawdown(pd.Series([100.0, 110.0], index=[0, 1]))

    def test_데이터가_1건이면_예외없이_0(self):
        equity = _series([100])

        assert calc_volatility(equity) == pytest.approx(0.0)
        assert calc_sharpe_ratio(equity) == pytest.approx(0.0)
        assert calc_cagr(equity) == pytest.approx(0.0)