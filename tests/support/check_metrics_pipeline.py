"""
지표 파이프라인 수동 점검 스크립트 (통합 테스트 전 단계)

pytest 가 아니라 눈으로 확인하기 위한 용도.
각 단계에서 실패하면 그 지점에서 멈추고 원인을 출력한다.

실행:
    python -m tests.support.check_metrics_pipeline

환경:
    conftest.py 가 적용되지 않으므로 DB_URL 은 아래 상수에서 직접 오버라이드한다.
"""

from __future__ import annotations

import asyncio
from datetime import date

# ─────────────────────────────────────────────────────────────
# 설정 오버라이드 (import 순서 중요: app.db.session 보다 먼저)
# ─────────────────────────────────────────────────────────────
from app.core.enums import MARKET_INDEX_CODE
from app.core.settings import settings

settings.DB_URL = "postgresql+asyncpg://postgres:1q2w3e4r!!@localhost:5432/postgres"
settings.DB_HOST = "localhost"

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.market.provider.fdr_provider import FDRMarketDataProvider  # noqa: E402
from app.repository.portfolio_snapshot_repository import (  # noqa: E402
    get_holdings_by_snapshot_ids,
    get_snapshots_by_period,
)
from app.strategy.metrics.adapters import (  # noqa: E402
    build_benchmark_series,
    build_equity_series,
    load_rebalance_dates,
    load_trade_values,
)
from app.strategy.metrics.core import (  # noqa: E402
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
# 점검 대상 (샘플 데이터에 맞춰 수정)
# ─────────────────────────────────────────────────────────────
ACCOUNT_NO = "50000000"
ACCOUNT_PRODUCT_CODE = "01"
START_DATE = date(2026, 4, 1)
AS_OF_DATE = date(2026, 4, 30)
BENCHMARK_CODE = MARKET_INDEX_CODE.KOSPI.value  # KS11

EXPECTED_INITIAL_NAV = 10_000_000    # t0 NAV 기대값. 검증용 참고치


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# ─────────────────────────────────────────────────────────────
# 1단계: 스냅샷 조회
# ─────────────────────────────────────────────────────────────
async def step1_snapshots(db) -> list:
    _section("1단계  스냅샷 조회")

    snapshots = await get_snapshots_by_period(
        db=db,
        account_no=ACCOUNT_NO,
        account_product_code=ACCOUNT_PRODUCT_CODE,
        start_date=START_DATE,
        end_date=AS_OF_DATE,
    )
    print(f"스냅샷 {len(snapshots)}건")

    if not snapshots:
        print("\n[중단] 스냅샷 0건. 아래를 확인하세요.")
        print("  - account_no / account_product_code 값")
        print("  - trading_date 가 NULL 인지 (필터가 trading_date 기준)")
        print("  - 조회 기간")
        return []

    for s in snapshots:
        print(
            f"  {s.trading_date}  type={s.snapshot_type}  "
            f"cash={s.cash_amount:,}  rebalance_id={s.rebalance_id}"
        )

    holdings = await get_snapshot_holdings_flat(db, [s.id for s in snapshots])
    print(f"\n보유종목 {len(holdings)}건")
    for h in holdings:
        print(
            f"  {h.stock_code}  {h.stock_name}  "
            f"qty={h.holding_qty}  buy={h.avg_buy_price}  cur={h.current_price}"
        )

    return snapshots


async def get_snapshot_holdings_flat(db, snapshot_ids):
    return await get_holdings_by_snapshot_ids(db=db, snapshot_ids=snapshot_ids)


# ─────────────────────────────────────────────────────────────
# 2단계: FDR 종가 조회
# ─────────────────────────────────────────────────────────────
def step2_fdr(codes: list[str]) -> bool:
    _section("2단계  FDR 종가 조회")

    provider = FDRMarketDataProvider()
    ok = True

    for code in codes:
        try:
            df = provider.get_ohlcv(
                code, START_DATE.isoformat(), AS_OF_DATE.isoformat()
            )
            if df is None or df.empty:
                print(f"  {code}  [실패] 빈 데이터")
                ok = False
                continue

            close_col = df["Close"]
            print(
                f"  {code}  {len(df)}행  "
                f"first={close_col.iloc[0]:,.0f}  last={close_col.iloc[-1]:,.0f}"
            )
        except Exception as e:
            print(f"  {code}  [실패] {type(e).__name__}: {e}")
            ok = False

    if not ok:
        print("\n[경고] 조회 실패 종목이 있습니다. 종목코드 6자리 포맷을 확인하세요.")

    return ok


# ─────────────────────────────────────────────────────────────
# 3단계: equity Series 조립
# ─────────────────────────────────────────────────────────────
async def step3_equity(db):
    _section("3단계  equity Series 조립")

    equity = await build_equity_series(
        db=db,
        account_no=ACCOUNT_NO,
        account_product_code=ACCOUNT_PRODUCT_CODE,
        start_date=START_DATE,
        as_of_date=AS_OF_DATE,
    )

    print(f"길이           : {len(equity)}  (거래일 수)")
    print(f"기간           : {equity.index[0].date()} ~ {equity.index[-1].date()}")
    print(f"결측치         : {int(equity.isna().sum())}건")
    print(f"인덱스 오름차순: {equity.index.is_monotonic_increasing}")

    initial = float(equity.iloc[0])
    diff_pct = (initial / EXPECTED_INITIAL_NAV - 1) * 100
    print(f"\nt0 NAV         : {initial:,.0f}")
    print(f"기대값 대비     : {diff_pct:+.2f}%  (기대 {EXPECTED_INITIAL_NAV:,})")

    if abs(diff_pct) > 1:
        print("  → 지정 단가와 실제 종가가 다릅니다. 비율만 맞으면 지표 검증에는 무방.")

    print(f"\n최종 NAV       : {float(equity.iloc[-1]):,.0f}")
    print(f"최고 NAV       : {float(equity.max()):,.0f}")
    print(f"최저 NAV       : {float(equity.min()):,.0f}")

    print("\n--- 앞 5일 ---")
    print(equity.head().to_string())
    print("\n--- 뒤 5일 ---")
    print(equity.tail().to_string())

    return equity


# ─────────────────────────────────────────────────────────────
# 4단계: 지표 산출
# ─────────────────────────────────────────────────────────────
async def step4_metrics(db, equity) -> None:
    _section("4단계  지표 산출")

    rebalance_dates = await load_rebalance_dates(
        db=db, start_date=START_DATE, as_of_date=AS_OF_DATE
    )
    print(f"리밸런싱 실행일: {rebalance_dates}\n")

    total_return = calc_total_return(equity)
    cagr = calc_cagr(equity)
    mdd = calc_max_drawdown(equity)
    dd = calc_drawdown_duration(equity)
    vol = calc_volatility(equity)
    sharpe = calc_sharpe_ratio(equity)

    print(f"총수익률       : {total_return * 100:>8.2f} %")
    print(f"CAGR           : {cagr * 100:>8.2f} %")
    print(f"MDD            : {mdd * 100:>8.2f} %")
    print(f"연율 변동성    : {vol * 100:>8.2f} %")
    print(f"Sharpe         : {sharpe:>8.2f}")
    print(
        f"낙폭 지속일    : 최대 {dd.max_days}일 / "
        f"미회복 {dd.current_days}일 / 회복여부 {dd.is_recovered}"
    )

    if mdd == 0:
        print("\n  [확인] MDD 0%. 해당 기간에 낙폭이 없습니다.")
        print("         낙폭 검증이 목적이라면 기간이나 종목 구성을 조정하세요.")

    # ── 승률 / 손익비 ──
    period_returns = calc_rebalance_period_returns(equity, rebalance_dates)
    win = calc_win_metrics(period_returns)

    print(f"\n구간 수익률    : {[f'{r * 100:.2f}%' for r in period_returns]}")
    print(f"구간 수         : {win.period_count}")
    print(f"승률            : {win.win_rate * 100:.2f} %")
    print(f"평균 수익 구간  : {win.avg_win * 100:.2f} %")
    print(f"평균 손실 구간  : {win.avg_loss * 100:.2f} %")
    print(f"Profit Factor   : {win.profit_factor}")

    if win.profit_factor is None:
        print("  → 손실 구간 0건. None 반환이 정상 (0.0 이면 버그).")
    if win.period_count <= 1:
        print("  → 구간 1개 이하. 승률은 0% 또는 100% 만 나옵니다.")

    # ── 회전율 ──
    buy_value, sell_value = await load_trade_values(
        db=db,
        account_no=ACCOUNT_NO,
        account_product_code=ACCOUNT_PRODUCT_CODE,
        start_date=START_DATE,
        as_of_date=AS_OF_DATE,
    )
    turnover = calc_turnover(equity, buy_value, sell_value)

    print(f"\n총 매수금액     : {turnover.total_buy_value:,.0f}")
    print(f"총 매도금액     : {turnover.total_sell_value:,.0f}")
    print(f"평균 NAV        : {turnover.avg_nav:,.0f}")
    print(f"회전율          : {turnover.turnover_rate * 100:.2f} %")

    if turnover.total_sell_value == 0:
        print("  → 매도 0건. min(매수,매도) 정의상 회전율 0%가 정상.")

    # ── Alpha ──
    try:
        benchmark = await build_benchmark_series(
            start_date=START_DATE,
            as_of_date=AS_OF_DATE,
            benchmark_code=BENCHMARK_CODE,
        )
        alpha = calc_alpha(equity, benchmark)
        benchmark_cagr = calc_cagr(benchmark)

        print(f"\n벤치마크        : {BENCHMARK_CODE}  ({len(benchmark)}행)")
        print(f"벤치마크 CAGR   : {benchmark_cagr * 100:>8.2f} %")
        print(f"Alpha (초과CAGR): {alpha * 100:>8.2f} %")
    except Exception as e:
        print(f"\n[벤치마크 실패] {type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────
async def main() -> None:
    print(f"계좌   : {ACCOUNT_NO}-{ACCOUNT_PRODUCT_CODE}")
    print(f"기간   : {START_DATE} ~ {AS_OF_DATE}")

    async with AsyncSessionLocal() as db:
        snapshots = await step1_snapshots(db)
        if not snapshots:
            return

        holdings = await get_snapshot_holdings_flat(db, [s.id for s in snapshots])
        codes = sorted({str(h.stock_code).strip().zfill(6) for h in holdings})

        if not step2_fdr(codes):
            print("\n[중단] FDR 조회 실패로 진행 불가.")
            return

        equity = await step3_equity(db)
        await step4_metrics(db, equity)

    _section("완료")


if __name__ == "__main__":
    asyncio.run(main())