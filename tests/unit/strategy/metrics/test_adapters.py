"""
어댑터 조립 로직 단위 테스트

DB / FDR 의존 없음. assemble_equity 는 순수 함수이므로
SnapshotView 와 종가 DataFrame 을 직접 만들어 검증한다.

DB·FDR 이 붙는 build_equity_series 는 통합 테스트에서 다룬다.
"""

from datetime import date

import pandas as pd
import pytest

from app.strategy.metrics.adapters import (
    SnapshotView,
    _normalize_stock_code,
    assemble_equity,
)


# ─────────────────────────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────────────────────────
@pytest.fixture
def close_frame() -> pd.DataFrame:
    """
    거래일 3일치 종가.
              005930    000660
    04-01     180,000   900,000
    04-02     190,000   910,000
    04-03     170,000   890,000
    """
    return pd.DataFrame(
        {
            "005930": [180_000.0, 190_000.0, 170_000.0],
            "000660": [900_000.0, 910_000.0, 890_000.0],
        },
        index=pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-03"]),
    )


@pytest.fixture
def snapshot_r1() -> SnapshotView:
    """삼성전자 11주 + 하이닉스 2주 + 현금 570,000"""
    return SnapshotView(
        trading_date=date(2026, 4, 1),
        cash_amount=570_000.0,
        holdings={"005930": 11, "000660": 2},
    )


# ─────────────────────────────────────────────────────────────
# NAV 조립
# ─────────────────────────────────────────────────────────────
class TestAssembleEquity:
    def test_단일_스냅샷_전_구간_수량_유지(self, snapshot_r1, close_frame):
        equity = assemble_equity([snapshot_r1], close_frame, date(2026, 4, 3))

        assert len(equity) == 3
        # 11×180,000 + 2×900,000 + 570,000
        assert equity.iloc[0] == pytest.approx(4_350_000)
        # 11×190,000 + 2×910,000 + 570,000
        assert equity.iloc[1] == pytest.approx(4_480_000)
        # 11×170,000 + 2×890,000 + 570,000
        assert equity.iloc[2] == pytest.approx(4_220_000)

    def test_스냅샷_당일부터_새_수량이_적용된다(self, snapshot_r1, close_frame):
        """리밸런싱 당일은 직전 스냅샷이 아니라 당일 스냅샷 수량을 쓴다."""
        snapshot_r2 = SnapshotView(
            trading_date=date(2026, 4, 3),
            cash_amount=100_000.0,
            holdings={"000660": 4},  # 삼성전자 전량 매도, 하이닉스 증량
        )

        equity = assemble_equity(
            [snapshot_r1, snapshot_r2], close_frame, date(2026, 4, 3)
        )

        # 04-02 까지는 R1 수량
        assert equity.iloc[1] == pytest.approx(4_480_000)
        # 04-03 부터 R2 수량: 4×890,000 + 100,000
        assert equity.iloc[2] == pytest.approx(3_660_000)

    def test_스냅샷에서_사라진_종목은_0으로_처리된다(self, snapshot_r1, close_frame):
        snapshot_r2 = SnapshotView(
            trading_date=date(2026, 4, 3),
            cash_amount=0.0,
            holdings={"005930": 11},  # 하이닉스 없음
        )

        equity = assemble_equity(
            [snapshot_r1, snapshot_r2], close_frame, date(2026, 4, 3)
        )

        # 11×170,000 + 0 + 0
        assert equity.iloc[2] == pytest.approx(1_870_000)

    def test_as_of_이후_거래일은_제외된다(self, snapshot_r1, close_frame):
        equity = assemble_equity([snapshot_r1], close_frame, date(2026, 4, 2))

        assert len(equity) == 2
        assert equity.index[-1] == pd.Timestamp("2026-04-02")

    def test_스냅샷_이전_거래일은_제외된다(self, close_frame):
        snapshot = SnapshotView(
            trading_date=date(2026, 4, 2),
            cash_amount=0.0,
            holdings={"005930": 10},
        )

        equity = assemble_equity([snapshot], close_frame, date(2026, 4, 3))

        assert len(equity) == 2
        assert equity.index[0] == pd.Timestamp("2026-04-02")

    def test_스냅샷_순서가_뒤바뀌어도_결과는_같다(self, snapshot_r1, close_frame):
        snapshot_r2 = SnapshotView(
            trading_date=date(2026, 4, 3),
            cash_amount=100_000.0,
            holdings={"000660": 4},
        )

        ordered = assemble_equity(
            [snapshot_r1, snapshot_r2], close_frame, date(2026, 4, 3)
        )
        reversed_ = assemble_equity(
            [snapshot_r2, snapshot_r1], close_frame, date(2026, 4, 3)
        )

        pd.testing.assert_series_equal(ordered, reversed_)

    def test_반환_시리즈는_core_입력_계약을_만족한다(self, snapshot_r1, close_frame):
        equity = assemble_equity([snapshot_r1], close_frame, date(2026, 4, 3))

        assert isinstance(equity.index, pd.DatetimeIndex)
        assert equity.index.is_monotonic_increasing
        assert not equity.isna().any()
        assert (equity > 0).all()


# ─────────────────────────────────────────────────────────────
# 예외
# ─────────────────────────────────────────────────────────────
class TestAssembleEquityErrors:
    def test_스냅샷이_없으면_예외(self, close_frame):
        with pytest.raises(ValueError):
            assemble_equity([], close_frame, date(2026, 4, 3))

    def test_종가가_비어있으면_예외(self, snapshot_r1):
        with pytest.raises(ValueError):
            assemble_equity([snapshot_r1], pd.DataFrame(), date(2026, 4, 3))

    def test_기간에_거래일이_없으면_예외(self, close_frame):
        snapshot = SnapshotView(
            trading_date=date(2026, 5, 1),  # 종가 데이터 범위 밖
            cash_amount=0.0,
            holdings={"005930": 10},
        )

        with pytest.raises(ValueError):
            assemble_equity([snapshot], close_frame, date(2026, 5, 10))


# ─────────────────────────────────────────────────────────────
# 종목코드 정규화
# ─────────────────────────────────────────────────────────────
class TestNormalizeStockCode:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("005930", "005930"),
            ("5930", "005930"),
            (" 005930 ", "005930"),
            ("660", "000660"),
        ],
    )
    def test_6자리로_정규화(self, raw, expected):
        assert _normalize_stock_code(raw) == expected