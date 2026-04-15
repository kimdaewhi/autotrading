"""
⭐ 리밸런싱 파이프라인 통합테스트 (dry_run=True)

실제 API를 호출하여 전체 파이프라인이 정상 동작하는지 검증한다.
    - 1단계: F-Score 스크리닝 (DART API)
    - 2단계: OHLCV 로딩 + 모멘텀 시그널 (FinanceDataReader)
    - 3단계: 계좌 보유 현황 조회 (KIS API)
    - 4단계: 포지션 diff 계산
    
dry_run=True이므로 실제 주문은 생성되지 않는다.
일요일/장 마감 후에도 1~4단계 검증은 가능하다.

실행 방법:
    pytest tests/integration/test_rebalance_integration.py -v -s
    
주의:
    - 실제 네트워크 호출이 발생한다 (DART, FinanceDataReader, KIS API)
    - 실행 시간이 수 분 걸릴 수 있다
    - KIS 인증 토큰이 필요하다 (Redis에 캐시되어 있거나 발급 가능해야 함)
"""

import asyncio
import pytest
import redis.asyncio as redis

from app.broker.kis.kis_account import KISAccount
from app.broker.kis.kis_auth import KISAuth
from app.core.enums import STRATEGY_SIGNAL
from app.core.settings import settings
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.services.kis.account_service import AccountService
from app.services.kis.auth_service import AuthService
from app.strategy.live.position_diff import (
    CurrentHolding,
    PositionDiffCalculator,
    PositionDiffResult,
)
from app.strategy.live.order_generator import OrderGenerator
from app.strategy.live.rebalance_service import RebalanceService
from app.strategy.screener.fscore import FScore
from app.strategy.signals.momentum import MomentumStrategy


# ── Fixtures ──

@pytest.fixture(scope="module")
def event_loop():
    """모듈 단위 이벤트 루프 (async 테스트용)"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def fdr_provider():
    return FDRMarketDataProvider()


@pytest.fixture(scope="module")
def account_service():
    kis_account = KISAccount(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )
    return AccountService(kis_account=kis_account)


@pytest.fixture(scope="module")
def screener():
    return FScore(threshold=7)


@pytest.fixture(scope="module")
def strategy():
    return MomentumStrategy(lookback_days=120, top_n=10)


@pytest.fixture(scope="module")
def rebalance_service(screener, strategy, account_service, fdr_provider):
    return RebalanceService(
        screener=screener,
        strategy=strategy,
        account_service=account_service,
        data_provider=fdr_provider,
    )


# ── 단계별 개별 테스트 ──

class TestStep1Screening:
    """1단계: F-Score 스크리닝 검증"""
    
    @pytest.mark.asyncio
    async def test_fscore_screening(self, screener):
        """F-Score 스크리닝이 유니버스를 반환하는지 확인"""
        df_universe = await screener.screen(year=2024)
        
        assert not df_universe.empty, "유니버스가 비어있음"
        assert "code" in df_universe.columns, "code 컬럼 누락"
        assert "Name" in df_universe.columns, "Name 컬럼 누락"
        assert "fscore" in df_universe.columns, "fscore 컬럼 누락"
        assert (df_universe["fscore"] >= 7).all(), "threshold 미만 종목 포함"
        
        print(f"\n✅ 유니버스: {len(df_universe)}종목 통과")
        print(f"   F-Score 범위: {df_universe['fscore'].min()} ~ {df_universe['fscore'].max()}")


class TestStep2Signal:
    """2단계: OHLCV 로딩 + 모멘텀 시그널 생성 검증"""
    
    @pytest.mark.asyncio
    async def test_momentum_signal(self, screener, strategy, fdr_provider):
        """모멘텀 시그널이 정상 생성되는지 확인"""
        import pandas as pd
        
        # 스크리닝
        df_universe = await screener.screen(year=2024)
        stock_codes = df_universe["code"].tolist()
        
        # OHLCV 로딩 (상위 20종목만 — 시간 절약)
        today = pd.Timestamp.today().strftime("%Y-%m-%d")
        lookback_start = (
            pd.Timestamp.today() - pd.tseries.offsets.BDay(150)
        ).strftime("%Y-%m-%d")
        
        data = {}
        for code in stock_codes[:20]:
            try:
                df = fdr_provider.get_ohlcv(code, lookback_start, today)
                if df.empty:
                    continue
                df["Date"] = pd.to_datetime(df["Date"])
                df.set_index("Date", inplace=True)
                data[code] = df
            except Exception:
                continue
        
        assert len(data) > 0, "OHLCV 로딩 실패"
        
        # 시그널 생성
        signal_df = strategy.generate_signal(data)
        
        assert not signal_df.empty, "시그널 결과 비어있음"
        assert "signal" in signal_df.columns, "signal 컬럼 누락"
        assert "return" in signal_df.columns, "return 컬럼 누락"
        assert "rank" in signal_df.columns, "rank 컬럼 누락"
        
        buy_count = (signal_df["signal"] == STRATEGY_SIGNAL.BUY).sum()
        print(f"\n✅ 시그널 생성: {len(signal_df)}종목 중 BUY {buy_count}종목")
        print(signal_df[signal_df["signal"] == STRATEGY_SIGNAL.BUY].head(10))


class TestStep3Account:
    """3단계: 계좌 보유 현황 조회 검증"""
    
    @pytest.mark.asyncio
    async def test_holding_list(self, account_service):
        """보유 종목 조회가 정상 동작하는지 확인"""
        holdings = await account_service.get_holding_list()
        
        # 보유 종목이 없을 수도 있음 (정상)
        print(f"\n✅ 보유 종목: {len(holdings)}종목")
        for h in holdings:
            print(f"   {h.stock_code} {h.stock_name}: {h.holding_qty}주 (현재가: {h.current_price})")
    
    @pytest.mark.asyncio
    async def test_account_summary(self, account_service):
        """계좌 요약 조회가 정상 동작하는지 확인"""
        summary = await account_service.get_account_summary()
        
        assert summary.cash_amount is not None, "예수금 조회 실패"
        
        cash = int(summary.cash_amount)
        print(f"\n✅ 예수금: {cash:,}원")
        print(f"   총 평가: {summary.total_evaluation_amount}")


class TestStep4Diff:
    """4단계: 포지션 diff 계산 검증 (실제 계좌 데이터 기반)"""
    
    @pytest.mark.asyncio
    async def test_position_diff_with_real_data(self, account_service):
        """실제 계좌 데이터로 diff 계산이 정상 동작하는지 확인"""
        # 계좌 데이터 조회
        holdings_raw = await account_service.get_holding_list()
        current_holdings = [
            CurrentHolding(
                stock_code=h.stock_code,
                stock_name=h.stock_name,
                quantity=int(h.holding_qty),
                current_price=int(h.current_price),
                eval_amount=int(h.evaluation_amount),
            )
            for h in holdings_raw
        ]
        
        summary = await account_service.get_account_summary()
        available_cash = int(summary.cash_amount)
        
        # 가상 BUY 시그널 (테스트용)
        import pandas as pd
        buy_codes = ["005930", "035720", "000660"]
        signal_df = pd.DataFrame({
            "return": [0.15, 0.10, 0.08],
            "rank": [1, 2, 3],
            "signal": [STRATEGY_SIGNAL.BUY] * 3,
        }, index=buy_codes)
        
        price_map = {"005930": 55000, "035720": 47000, "000660": 180000}
        name_map = {"005930": "삼성전자", "035720": "카카오", "000660": "SK하이닉스"}
        
        # diff 계산
        calc = PositionDiffCalculator(cash_buffer_ratio=0.02)
        diff_result = calc.calculate(
            buy_codes=buy_codes,
            signal_df=signal_df,
            current_holdings=current_holdings,
            available_cash=available_cash,
            price_map=price_map,
            name_map=name_map,
        )
        
        assert diff_result is not None
        assert diff_result.estimated_cash_after >= 0, "잔여 현금이 음수"
        
        print(f"\n{diff_result.summary()}")


# ── 전체 파이프라인 통합 테스트 ──

class TestFullPipeline:
    """전체 파이프라인 통합 테스트 (dry_run=True)"""
    
    @pytest.mark.asyncio
    async def test_full_rebalance_dry_run(self, rebalance_service):
        """
        전체 리밸런싱 파이프라인을 dry_run=True로 실행
        1~4단계 전체가 정상 동작하는지 검증
        """
        result = await rebalance_service.run(
            year=2024,
            dry_run=True,
        )
        
        # 기본 검증
        assert result.rebalance_id, "rebalance_id 누락"
        assert result.executed_at, "executed_at 누락"
        assert result.dry_run is True
        
        # 파이프라인 결과 검증
        assert result.universe_count > 0, "유니버스가 비어있음"
        assert result.signal_buy_count > 0, f"BUY 시그널 없음 (error: {result.error_message})"
        
        # diff 결과 검증
        assert result.diff_result is not None, "diff 결과 없음"
        assert result.diff_result.estimated_cash_after >= 0, "잔여 현금 음수"
        
        # 주문은 생성되지 않아야 함 (dry_run)
        assert result.order_result is None, "dry_run인데 주문 결과가 있음"
        
        assert result.success is True, f"실패: {result.error_message}"
        
        # 전체 결과 출력
        print(f"\n{result.summary()}")


    @pytest.mark.asyncio
    async def test_full_rebalance_live(self, rebalance_service):
        """dry_run=False 실제 주문 생성 테스트 (장 마감 시 FAILED 예상)"""
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await rebalance_service.run(
                year=2024,
                dry_run=False,
                db=db,
            )
        
        print(f"success: {result.success}")
        print(f"error: {result.error_message}")

        assert result.rebalance_id, "rebalance_id 누락"
        assert result.dry_run is False
        assert result.diff_result is not None, "diff 결과 없음"
        assert result.order_result is not None, "주문 결과 없음"
        assert result.order_result.total_orders > 0, "주문이 생성되지 않음"

        print(f"\n{result.summary()}")