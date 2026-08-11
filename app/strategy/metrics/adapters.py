"""
지표 계산 입력 어댑터

repository(DB) 와 FDRMarketDataProvider(시세) 를 호출해
core.py 가 요구하는 입력 형태로 조립한다.

    스냅샷 + FDR 종가  ─→  equity: pd.Series
    rebalances        ─→  rebalance_dates: list[date]
    FDR(KS11)         ─→  benchmark: pd.Series
    orders            ─→  (총 매수금액, 총 매도금액)

조회 로직은 전부 repository 에 위임한다. 여기서 ORM 을 직접 쓰지 않는다.

NAV 재구성 방식:
    NAV(t) = Σ(보유수량(t) × 종가(t)) + 현금(t)
    보유수량/현금은 리밸런싱 시점 스냅샷을 forward-fill 한다.
    (리밸런싱 사이에는 수량이 변하지 않는다는 가정)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.repository.order_repository import get_filled_orders_by_period
from app.repository.portfolio_snapshot_repository import (
    get_holdings_by_snapshot_ids,
    get_snapshots_by_period,
)
from app.repository.rebalance_repository import get_completed_rebalance_dates

KST = ZoneInfo("Asia/Seoul")

DEFAULT_BENCHMARK_CODE = "KS11"          # KOSPI. KOSPI200 은 "KS200"
SNAPSHOT_TYPE_REBALANCE = "REBALANCE"


# ─────────────────────────────────────────────────────────────
# 중간 표현
#   DB 모델과 pandas 사이의 완충. 조립 함수를 순수 함수로 유지하기 위함.
# ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SnapshotView:
    trading_date: date
    cash_amount: float
    holdings: dict[str, int]        # {종목코드(6자리): 보유수량}


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────
def _normalize_stock_code(code: str) -> str:
    """DB 는 varchar(20), FDR 은 6자리를 기대하므로 zero-padding 정규화."""
    return str(code).strip().zfill(6)


def _resolve_trading_date(snapshot) -> date:
    """trading_date 가 비어 있으면 snapshot_at 을 KST 날짜로 환산해 대체."""
    if snapshot.trading_date is not None:
        return snapshot.trading_date
    return snapshot.snapshot_at.astimezone(KST).date()


async def _fetch_close_series(
    provider: FDRMarketDataProvider,
    code: str,
    start: date,
    end: date,
) -> pd.Series:
    """
    단일 종목 종가 시계열.

    FDR 호출은 동기 블로킹이므로 스레드로 넘긴다.
    (joblib 디스크 캐시가 걸려 있어 두 번째 호출부터는 사실상 즉시 반환)
    """
    df = await asyncio.to_thread(
        provider.get_ohlcv, code, start.isoformat(), end.isoformat()
    )
    if df is None or df.empty:
        return pd.Series(dtype="float64")

    # get_ohlcv 는 reset_index() 된 DataFrame 을 반환한다.
    frame = df.copy()
    if "Date" in frame.columns:
        frame = frame.set_index("Date")

    frame.index = pd.to_datetime(frame.index)
    return frame["Close"].astype("float64").sort_index()


async def _build_close_frame(
    provider: FDRMarketDataProvider,
    codes: list[str],
    start: date,
    end: date,
) -> pd.DataFrame:
    """
    종목별 종가를 하나의 DataFrame(index=거래일, columns=종목코드)으로 조립.

    거래정지 등으로 특정 종목의 날짜가 비면 직전 종가로 채운다(ffill).
    조회 자체가 실패한 종목은 예외를 던져 조용한 오류를 막는다.
    """
    series_map: dict[str, pd.Series] = {}

    for code in codes:
        series = await _fetch_close_series(provider, code, start, end)
        if series.empty:
            raise ValueError(f"FDR 종가 조회 실패 - 데이터 없음. code={code}")
        series_map[code] = series

    frame = pd.DataFrame(series_map).sort_index()
    return frame.ffill()


def assemble_equity(
    snapshots: list[SnapshotView],
    close_frame: pd.DataFrame,
    as_of_date: date,
) -> pd.Series:
    """
    스냅샷과 종가로 일별 NAV 시계열을 조립한다. (순수 함수, DB/FDR 무관)

    close_frame : index=거래일(DatetimeIndex), columns=종목코드, values=종가
    """
    if not snapshots:
        raise ValueError("스냅샷이 없습니다.")
    if close_frame.empty:
        raise ValueError("종가 데이터가 비어 있습니다.")

    ordered = sorted(snapshots, key=lambda s: s.trading_date)
    first_date = pd.Timestamp(ordered[0].trading_date)
    last_date = pd.Timestamp(as_of_date)

    trading_days = close_frame.index[
        (close_frame.index >= first_date) & (close_frame.index <= last_date)
    ]
    if len(trading_days) == 0:
        raise ValueError("해당 기간에 거래일이 없습니다.")

    codes = list(close_frame.columns)
    snapshot_index = pd.DatetimeIndex([pd.Timestamp(s.trading_date) for s in ordered])

    # 스냅샷 시점의 수량/현금 → 거래일 인덱스로 forward-fill
    qty_frame = pd.DataFrame(
        [[s.holdings.get(code, 0) for code in codes] for s in ordered],
        index=snapshot_index,
        columns=codes,
        dtype="float64",
    )
    cash_series = pd.Series(
        [s.cash_amount for s in ordered], index=snapshot_index, dtype="float64"
    )

    merged_index = snapshot_index.union(trading_days)
    qty_frame = qty_frame.reindex(merged_index).ffill().reindex(trading_days).fillna(0.0)
    cash_series = (
        cash_series.reindex(merged_index).ffill().reindex(trading_days).fillna(0.0)
    )

    closes = close_frame.loc[trading_days, codes]
    equity = (closes * qty_frame).sum(axis=1) + cash_series

    equity.name = "equity"
    return equity.astype("float64")


# ─────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────
async def build_equity_series(
    db: AsyncSession,
    account_no: str,
    account_product_code: str,
    start_date: date,
    as_of_date: date,
    provider: FDRMarketDataProvider | None = None,
) -> pd.Series:
    """스냅샷 + FDR 종가로 일별 NAV 시계열을 만든다."""
    provider = provider or FDRMarketDataProvider()

    snapshots = await get_snapshots_by_period(
        db=db,
        account_no=account_no,
        account_product_code=account_product_code,
        start_date=start_date,
        end_date=as_of_date,
    )
    if not snapshots:
        raise ValueError(
            f"스냅샷이 없습니다. account_no={account_no}, "
            f"기간={start_date}~{as_of_date}"
        )

    snapshot_ids = [s.id for s in snapshots]
    holdings = await get_holdings_by_snapshot_ids(db=db, snapshot_ids=snapshot_ids)
    
    # 스냅샷별 보유 종목을 {snapshot_id: {code: qty}} 형태로 그룹화
    grouped: dict[object, dict[str, int]] = {sid: {} for sid in snapshot_ids}
    for row in holdings:
        code = _normalize_stock_code(row.stock_code)
        grouped[row.snapshot_id][code] = int(row.holding_qty)

    views = [
        SnapshotView(
            trading_date=_resolve_trading_date(s),
            cash_amount=float(s.cash_amount or 0),
            holdings=grouped.get(s.id, {}),
        )
        for s in snapshots
    ]

    codes = sorted({code for v in views for code in v.holdings})
    if not codes:
        raise ValueError("스냅샷에 보유 종목이 없습니다.")

    close_frame = await _build_close_frame(
        provider=provider,
        codes=codes,
        start=min(v.trading_date for v in views),
        end=as_of_date,
    )

    return assemble_equity(views, close_frame, as_of_date)


async def build_benchmark_series(
    start_date: date,
    as_of_date: date,
    benchmark_code: str = DEFAULT_BENCHMARK_CODE,
    provider: FDRMarketDataProvider | None = None,
) -> pd.Series:
    """벤치마크 지수 종가 시계열. Alpha 계산용."""
    provider = provider or FDRMarketDataProvider()

    series = await _fetch_close_series(provider, benchmark_code, start_date, as_of_date)
    if series.empty:
        raise ValueError(f"벤치마크 조회 실패. code={benchmark_code}")

    series.name = "benchmark"
    return series


async def load_rebalance_dates(
    db: AsyncSession,
    start_date: date,
    as_of_date: date,
) -> list[date]:
    """리밸런싱 실행일 목록. 승률/손익비의 구간 경계로 쓰인다."""
    return await get_completed_rebalance_dates(
        db=db, start_date=start_date, end_date=as_of_date
    )


async def load_trade_values(
    db: AsyncSession,
    account_no: str,
    account_product_code: str,
    start_date: date,
    as_of_date: date,
) -> tuple[float, float]:
    """
    체결 기준 총 매수금액 / 총 매도금액. 회전율 입력.

    주문금액이 아니라 체결금액(filled_qty × avg_fill_price)을 쓴다.
    """
    rows = await get_filled_orders_by_period(
        db=db,
        account_no=account_no,
        account_product_code=account_product_code,
        start_date=start_date,
        end_date=as_of_date,
    )

    total_buy = 0.0
    total_sell = 0.0

    for order_pos, filled_qty, avg_fill_price in rows:
        if avg_fill_price is None or not filled_qty:
            continue

        amount = float(avg_fill_price) * int(filled_qty)
        if str(order_pos).strip().upper() == "BUY":
            total_buy += amount
        else:
            total_sell += amount

    return total_buy, total_sell