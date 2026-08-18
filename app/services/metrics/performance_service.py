"""
전략 성과 지표 서비스

adapters(입력 조립) + core(순수 계산) 를 묶어 API 응답 형태로 반환한다.

이 계층의 책임:
    - 기간 결정 (start_date ~ as_of_date)
    - 데이터 부족 시 None 처리 정책
    - core 계산 결과 → 응답 스키마 변환
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.schemas.strategy import metrics as metrics_schemas
from app.strategy.metrics import core
from app.strategy.metrics.adapters import (
    build_benchmark_series,
    build_equity_series,
    load_rebalance_dates,
    load_trade_values,
)
from app.core.enums import MARKET_INDEX_CODE
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ── 지표별 최소 요건 ──
# 기간이 짧으면 연율화 지표가 무의미한 값을 뱉으므로 None 으로 막는다.
MIN_DAYS_FOR_ANNUALIZED = 90        # CAGR / Alpha (달력일)
MIN_POINTS_FOR_RISK = 30            # 변동성 / 샤프 (거래일)
MIN_REBALANCES_FOR_TURNOVER = 2     # 회전율


class PerformanceService:
    """리밸런싱 전략의 성과 지표를 계산한다."""

    async def get_performance(
        self,
        db: AsyncSession,
        start_date: date,
        as_of_date: date | None = None,
    ) -> metrics_schemas.PerformanceRead:
        account_no = settings.KIS_ACCOUNT_NO
        account_product_code = settings.KIS_ACCOUNT_PRODUCT_CODE
        as_of = as_of_date or date.today()
        
        # ── 1. equity 조립 (스냅샷 없으면 빈 응답) ──
        try:
            equity = await build_equity_series(
                db=db,
                account_no=account_no,
                account_product_code=account_product_code,
                start_date=start_date,
                as_of_date=as_of,
            )
        except ValueError as e:
            logger.info(f"성과 지표 계산 불가 - 데이터 부족. reason={e}")
            return metrics_schemas.PerformanceRead.empty()
        
        if len(equity) < 2:
            logger.info(f"성과 지표 계산 불가 - 데이터 포인트 부족. count={len(equity)}")
            return metrics_schemas.PerformanceRead.empty()
        
        period_days = (equity.index[-1] - equity.index[0]).days
        
        # ── 2. 부가 입력 ──
        rebalance_dates = await load_rebalance_dates(
            db=db, start_date=start_date, as_of_date=as_of
        )
        total_buy, total_sell = await load_trade_values(
            db=db,
            account_no=account_no,
            account_product_code=account_product_code,
            start_date=start_date,
            as_of_date=as_of,
        )
        
        # 벤치마크는 equity 시작일 기준으로 맞춘다 (기간이 어긋나면 비교 불가)
        benchmark_start = equity.index[0].date()
        
        benchmark = None
        try:
            benchmark = await build_benchmark_series(
                start_date=benchmark_start, as_of_date=as_of
            )
        except ValueError as e:
            logger.warning(f"벤치마크 조회 실패 - Alpha 생략. error={e}")
            
        # KOSDAQ 은 화면 비교용 보조 지표. 실패해도 나머지 지표는 그대로 반환한다.
        benchmark_kosdaq = None
        try:
            benchmark_kosdaq = await build_benchmark_series(
                start_date=benchmark_start,
                as_of_date=as_of,
                benchmark_code=MARKET_INDEX_CODE.KOSDAQ.value,
            )
        except ValueError as e:
            logger.warning(f"KOSDAQ 벤치마크 조회 실패. error={e}")
        
        # ── 3. 계산 ──
        has_annualized = period_days >= MIN_DAYS_FOR_ANNUALIZED
        has_risk = len(equity) >= MIN_POINTS_FOR_RISK
        
        dd_duration = core.calc_drawdown_duration(equity)
        win = core.calc_win_metrics(
            core.calc_rebalance_period_returns(equity, rebalance_dates)
        )
        
        turnover = None
        if len(rebalance_dates) >= MIN_REBALANCES_FOR_TURNOVER:
            turnover = core.calc_turnover(
                equity=equity,
                total_buy_value=total_buy,
                total_sell_value=total_sell,
            )
        
        total_return = core.calc_total_return(equity)
        benchmark_return = (
            core.calc_total_return(benchmark) if benchmark is not None else None
        )
        benchmark_kosdaq_return = (
            core.calc_total_return(benchmark_kosdaq)
            if benchmark_kosdaq is not None
            else None
        )
        
        # NAV 시계열 조립
        period_profit = core.calc_period_profit(equity)
        # 벤치마크를 equity 거래일에 맞춘다. 없는 날은 NaN → None
        aligned_benchmark = (
            benchmark.reindex(equity.index) if benchmark is not None else None
        )
        
        
        # ── 4. 응답 조립 ──
        return metrics_schemas.PerformanceRead(
            period=metrics_schemas.Period(
                start=equity.index[0].date(),
                end=equity.index[-1].date(),
                days=period_days,
                trading_days=len(equity),
                rebalance_count=len(rebalance_dates),
            ),
            returns=metrics_schemas.ReturnMetrics(
                total_return=total_return,
                period_profit=period_profit,
                cagr=core.calc_cagr(equity) if has_annualized else None,
                benchmark_return=benchmark_return,
                benchmark_kosdaq_return=benchmark_kosdaq_return,
                alpha_vs_benchmark=(
                    core.calc_alpha(equity, benchmark)
                    if has_annualized and benchmark is not None
                    else None
                ),
                excess_return=(
                    total_return - benchmark_return
                    if total_return is not None and benchmark_return is not None
                    else None
                ),
            ),
            risk=metrics_schemas.RiskMetrics(
                max_drawdown=core.calc_max_drawdown(equity),
                mdd_max_days=dd_duration.max_days,
                mdd_current_days=dd_duration.current_days,
                is_recovered=dd_duration.is_recovered,
                volatility=core.calc_volatility(equity) if has_risk else None,
                sharpe_ratio=core.calc_sharpe_ratio(equity) if has_risk else None,
            ),
            trading=metrics_schemas.RebalanceTradeMetrics(
                period_count=win.period_count,
                win_rate=win.win_rate,
                avg_win=win.avg_win,
                avg_loss=win.avg_loss,
                profit_factor=win.profit_factor,
            ),
            turnover=metrics_schemas.TurnoverMetrics(
                turnover_rate=turnover.turnover_rate if turnover else None,
                total_buy_value=total_buy,
                total_sell_value=total_sell,
                avg_nav=turnover.avg_nav if turnover else None,
            ),
            nav_series=[
                metrics_schemas.NavPoint(
                    date=dt.date(),
                    nav=float(nav),
                    benchmark=(
                        float(aligned_benchmark.loc[dt])
                        if aligned_benchmark is not None
                        and pd.notna(aligned_benchmark.loc[dt])
                        else None
                    ),
                )
                for dt, nav in equity.items()
            ],
        )