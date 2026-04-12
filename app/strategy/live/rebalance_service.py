"""
⭐ Rebalance Service (Live Trading Pipeline)
    백테스트의 run_backtest()에 대응하는 실전매매 파이프라인 오케스트레이터
    
    전체 흐름:
        1. F-Score 스크리닝 → 유니버스 확보
        2. 유니버스 종목 OHLCV 로딩 → MomentumStrategy.generate_signal()
        3. 현재 보유 포트폴리오 조회 (KIS 계좌 API)
        4. PositionDiffCalculator → 매도/매수 diff 계산
        5. OrderGenerator → 주문 생성 + Celery 큐잉

    사용 예시:
        rebalance_service = RebalanceService(
            screener=FScore(threshold=7),
            strategy=MomentumStrategy(lookback_days=120, top_n=10),
            account_service=account_service,
            data_provider=provider,
        )
        
        # dry_run=True: 주문 생성 없이 리밸런싱 계획만 확인
        result = await rebalance_service.run(year=2024, dry_run=True)
        print(result.diff_result.summary())
        
        # 실제 주문 실행
        result = await rebalance_service.run(year=2024, dry_run=False)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import STRATEGY_SIGNAL
from app.db.models.rebalance import Rebalance
from app.strategy.live.position_diff import (
    CurrentHolding,
    PositionDiffCalculator,
    PositionDiffResult,
)
from app.strategy.live.order_generator import (
    OrderGenerator,
    OrderGenerationResult,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RebalanceResult:
    """리밸런싱 실행 결과"""
    rebalance_id: str = ""
    executed_at: str = ""
    
    # 파이프라인 단계별 결과
    universe_count: int = 0                     # 스크리닝 통과 종목 수
    signal_buy_count: int = 0                   # BUY 시그널 종목 수
    diff_result: PositionDiffResult | None = None
    order_result: OrderGenerationResult | None = None
    
    # 상태
    dry_run: bool = True
    success: bool = False
    error_message: str = ""
    
    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"🚀 리밸런싱 실행 결과",
            f"   실행 시각: {self.executed_at}",
            f"   rebalance_id: {self.rebalance_id}",
            f"   모드: {'DRY RUN (검증만)' if self.dry_run else '실전 주문'}",
            "=" * 60,
            f"📌 유니버스: {self.universe_count}종목 통과",
            f"📌 BUY 시그널: {self.signal_buy_count}종목",
        ]
        
        if self.diff_result:
            lines.append("")
            lines.append(self.diff_result.summary())
        
        if self.order_result:
            lines.append("")
            lines.append(self.order_result.summary())
        
        if self.error_message:
            lines.append(f"\n❌ 오류: {self.error_message}")
        
        return "\n".join(lines)


class RebalanceService:
    """
    ⭐ 실전매매 리밸런싱 서비스
    
    Parameters
    ----------
    screener : BaseScreener (FScore)
        유니버스 스크리너
    strategy : BaseStrategy (MomentumStrategy)
        매매 전략 (시그널 생성)
    account_service : AccountService
        KIS 계좌 API 서비스 (보유종목, 예수금 조회)
    data_provider : 
        OHLCV 데이터 제공자 (FinanceDataReader 또는 KIS API)
    diff_calculator : PositionDiffCalculator
        포지션 diff 계산기 (기본값 사용 가능)
    order_generator : OrderGenerator
        주문 생성기 (기본값 사용 가능)
    """
    
    def __init__(
        self,
        screener,
        strategy,
        account_service,
        data_provider,
        diff_calculator: PositionDiffCalculator | None = None,
        order_generator: OrderGenerator | None = None,
    ):
        self.screener = screener
        self.strategy = strategy
        self.account_service = account_service
        self.data_provider = data_provider
        self.diff_calculator = diff_calculator or PositionDiffCalculator()
        self.order_generator = order_generator or OrderGenerator()
    
    
    async def run(
        self,
        year: int,
        lookback_start: str | None = None,
        db: AsyncSession | None = None,
        dry_run: bool = True,
    ) -> RebalanceResult:
        """
        리밸런싱 전체 파이프라인 실행
        
        Parameters
        ----------
        year : F-Score 스크리닝 기준 사업연도
        lookback_start : 모멘텀 룩백 시작일 (None이면 자동 계산)
        db : SQLAlchemy async session (dry_run=False일 때 필수)
        dry_run : True면 diff 계산까지만 수행, 실제 주문은 생성하지 않음
        """
        import uuid
        
        rebalance_id = str(uuid.uuid4())
        result = RebalanceResult(
            rebalance_id=rebalance_id,
            executed_at=datetime.now().isoformat(),
            dry_run=dry_run,
        )
        
        try:
            # ⭐ 1단계: F-Score 스크리닝 → 유니버스 확보
            logger.info(f"[리밸런싱] 1단계: F-Score 스크리닝 (year={year})")
            df_universe = await self.screener.screen(year=year)
            result.universe_count = len(df_universe)
            logger.info(f"[리밸런싱] 유니버스 확보: {len(df_universe)}종목")
            
            if df_universe.empty:
                result.error_message = "F-Score 스크리닝 결과 종목이 없습니다."
                return result
            
            # 종목 코드/이름 매핑
            stock_codes = df_universe["code"].tolist()
            name_map = dict(zip(df_universe["code"], df_universe["Name"]))
            
            # ⭐ 2단계: OHLCV 데이터 로딩 + 모멘텀 시그널 생성
            logger.info(f"[리밸런싱] 2단계: OHLCV 로딩 + 모멘텀 시그널 생성")
            
            today = pd.Timestamp.today().strftime("%Y-%m-%d")
            
            # 룩백 시작일 자동 계산 (전략의 lookback_days 기반)
            if lookback_start is None:
                lookback_days = getattr(self.strategy, "lookback_days", 120)
                lookback_start = (
                    pd.Timestamp.today() - pd.tseries.offsets.BDay(lookback_days + 30)
                ).strftime("%Y-%m-%d")
            
            # OHLCV 데이터 로딩
            data = {}
            for code in stock_codes:
                try:
                    df = self.data_provider.get_ohlcv(code, lookback_start, today)
                    if df.empty:
                        continue
                    if "Date" in df.columns:
                        df["Date"] = pd.to_datetime(df["Date"])
                        df.set_index("Date", inplace=True)
                    data[code] = df
                except Exception as e:
                    logger.warning(f"[{code}] OHLCV 로딩 실패: {e}")
                    continue
            
            logger.info(f"[리밸런싱] OHLCV 로딩 완료: {len(data)}/{len(stock_codes)}종목")
            
            # 모멘텀 시그널 생성
            signal_df = self.strategy.generate_signal(data)
            buy_signals = signal_df[signal_df["signal"] == STRATEGY_SIGNAL.BUY]
            buy_codes = buy_signals.index.tolist()
            result.signal_buy_count = len(buy_codes)
            
            logger.info(f"[리밸런싱] BUY 시그널: {len(buy_codes)}종목")
            
            if not buy_codes:
                result.error_message = "BUY 시그널 종목이 없습니다. 전체 현금 보유 유지."
                # BUY가 없어도 기존 보유 종목 전량 매도는 수행해야 할 수 있음
                # 여기서는 일단 리턴 (정책에 따라 변경 가능)
                return result
            
            # ⭐ 3단계: 현재 보유 포트폴리오 조회
            logger.info(f"[리밸런싱] 3단계: 현재 보유 포트폴리오 조회")
            
            holdings_raw = await self.account_service.get_holding_list()
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
            
            # 예수금 조회
            account_summary = await self.account_service.get_account_summary()
            available_cash = int(account_summary.cash_amount)
            
            logger.info(
                f"[리밸런싱] 보유 현황: {len(current_holdings)}종목, "
                f"예수금: {available_cash:,}원"
            )
            
            # 신규 매수 종목의 현재가 매핑
            price_map = {}
            for code in buy_codes:
                if code in data and not data[code].empty:
                    price_map[code] = int(data[code]["Close"].iloc[-1])
                else:
                    logger.warning(f"[{code}] 현재가 확인 불가 - 매수 대상에서 제외될 수 있음")
            
            # ⭐ 4단계: 포지션 diff 계산
            logger.info(f"[리밸런싱] 4단계: 포지션 diff 계산")
            
            diff_result = self.diff_calculator.calculate(
                buy_codes=buy_codes,
                signal_df=signal_df,
                current_holdings=current_holdings,
                available_cash=available_cash,
                price_map=price_map,
                name_map=name_map,
            )
            result.diff_result = diff_result
            
            logger.info(f"\n{diff_result.summary()}")
            
            # dry_run이면 여기서 종료
            if dry_run:
                result.success = True
                logger.info("[리밸런싱] DRY RUN 완료 - 실제 주문은 생성하지 않음")
                return result
            
            # ⭐ 5단계: 주문 생성 + Celery 큐잉 + Rebalance 기록
            if db is None:
                result.error_message = "실제 주문 실행에는 DB 세션이 필요합니다."
                return result
            
            logger.info(f"[리밸런싱] 5단계: 주문 생성 및 제출")
            
            # 5-1. Rebalance 세션 기록
            rebalance_record = Rebalance(
                id=rebalance_id,
                strategy_name=self.strategy.__class__.__name__,
                screener_name=self.screener.__class__.__name__,
                universe_count=result.universe_count,
                buy_signal_count=result.signal_buy_count,
                sell_count=len(diff_result.sell_list),
                buy_count=len(diff_result.buy_list),
                hold_count=len(diff_result.hold_list),
                total_sell_value=diff_result.total_sell_value,
                total_buy_value=diff_result.total_buy_value,
                available_cash_before=available_cash,
                estimated_cash_after=diff_result.estimated_cash_after,
                dry_run=dry_run,
                status="RUNNING",
                strategy_params={
                    "lookback_days": getattr(self.strategy, "lookback_days", None),
                    "top_n": getattr(self.strategy, "top_n", None),
                    "abs_threshold": getattr(self.strategy, "abs_threshold", None),
                    "threshold": getattr(self.screener, "threshold", None),
                },
            )
            db.add(rebalance_record)
            await db.flush()
            
            # 5-2. 주문 생성 + 큐잉 (매도 체결 대기 → 매수 금액 재계산 → 매수 제출)
            order_result = self.order_generator.generate_orders(
                diff_result=diff_result,
                rebalance_id=rebalance_id,
            )
            result.order_result = order_result
            
            await self.order_generator.submit_orders(
                generation_result=order_result,
                db=db,
                account_service=self.account_service,
                buy_codes=buy_codes,
                signal_df=signal_df,
                hold_list=diff_result.hold_list,
                price_map=price_map,
                name_map=name_map,
            )
            
            # 5-3. Rebalance 상태 완료 처리
            rebalance_record.status = "COMPLETED"
            rebalance_record.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            result.success = True
            logger.info(f"[리밸런싱] 완료: {order_result.total_orders}건 주문 제출")
            
        except Exception as e:
            result.error_message = str(e)
            logger.error(f"[리밸런싱] 실패: {e}", exc_info=True)
            
            # Rebalance 기록이 있으면 FAILED로 업데이트
            if db is not None:
                try:
                    from sqlalchemy import update
                    await db.execute(
                        update(Rebalance)
                        .where(Rebalance.id == rebalance_id)
                        .values(status="FAILED", error_message=str(e))
                    )
                    await db.commit()
                except Exception:
                    pass  # 기록 실패는 무시
        
        return result