"""
⭐ Piotroski F-Score + Dual Momentum 조합 전략

    파이프라인:
        1. FScore.screen() → 재무 건전성 통과 종목 (유니버스)
        2. OHLCV 데이터 로딩
        3. MomentumStrategy.generate_signal() → BUY 시그널
        4. TradeIntent 리스트로 변환 → StrategyResult 반환

    사용 예시:
        strategy = PiotroskiMomentumStrategy(
            screener=FScore(threshold=7, universe_builder=...),
            momentum=MomentumStrategy(lookback_days=300, top_n=25),
            data_provider=FDRMarketDataProvider(),
        )
        result = await strategy.execute(year=2024)
"""

import pandas as pd

from app.core.enums import STRATEGY_SIGNAL
from app.market.provider.base_provider import BaseMarketDataProvider
from app.schemas.strategy.trading import (
    StrategyType,
    StrategyResult,
    TradeIntent,
    TradeSide,
)
from app.strategy.strategies.base_strategy import BaseStrategy
from app.strategy.screener.fscore import FScore
from app.strategy.signals.momentum import MomentumStrategy
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PiotroskiMomentumStrategy(BaseStrategy):
    """
    F-Score 스크리닝 + Dual Momentum 시그널 조합 전략

    - 스크리너(FScore)로 재무 건전성이 우수한 종목을 필터링한 뒤,
    - 모멘텀 시그널(MomentumStrategy)로 매수 타이밍을 잡아
    - 균등 비중 TradeIntent 리스트를 생성한다.
    """

    strategy_type = StrategyType.REBALANCE

    def __init__(
        self,
        screener: FScore,
        momentum: MomentumStrategy,
        data_provider: BaseMarketDataProvider,
    ):
        """
        Parameters
        ----------
        screener : FScore
            유니버스 스크리너 (재무 건전성 필터링)
        momentum : MomentumStrategy
            Dual Momentum 시그널 생성기
        data_provider :
            OHLCV 데이터 제공자 (FinanceDataReader 등)
        """
        self.screener = screener
        self.momentum = momentum
        self.data_provider = data_provider
    
    
    # ── BaseSignal 구현 (백테스트 호환) ──
    def generate_signal(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """모멘텀 시그널 생성 위임 — 백테스트에서 직접 호출 가능"""
        return self.momentum.generate_signal(data)
    
    
    # ⚙️ BaseStrategy 파이프라인 구현 (실전 매매)
    async def execute(self, year: int, **kwargs) -> StrategyResult:
        """
        전략 전체 파이프라인 실행
        
        Parameters
        ----------
        year : int
            F-Score 스크리닝 기준 사업연도
        
        Returns
        -------
        StrategyResult
            Executor가 처리할 TradeIntent 리스트
        """
        # ── 1단계: F-Score 스크리닝 ──
        logger.info(f"[{self.__class__.__name__}] 1단계: F-Score 스크리닝 (year={year})")
        df_universe = await self.screener.screen(year=year)
        
        if df_universe.empty:
            logger.warning(f"[{self.__class__.__name__}] 스크리닝 결과 종목 없음")
            return StrategyResult(
                strategy_type=self.strategy_type,
                strategy_name=self.__class__.__name__,
                metadata={"error": "스크리닝 결과 없음", "universe_count": 0},
            )
        
        stock_codes = df_universe["code"].tolist()
        name_map = dict(zip(df_universe["code"], df_universe["Name"]))
        logger.info(f"[{self.__class__.__name__}] 유니버스 확보: {len(stock_codes)}종목")
        
        # ── 2단계: OHLCV 데이터 로딩 ──
        logger.info(f"[{self.__class__.__name__}] 2단계: OHLCV 로딩")
        data = self._load_ohlcv(stock_codes)
        logger.info(
            f"[{self.__class__.__name__}] OHLCV 로딩 완료: "
            f"{len(data)}/{len(stock_codes)}종목"
        )
        
        # ── 3단계: 모멘텀 시그널 생성 ──
        logger.info(f"[{self.__class__.__name__}] 3단계: 모멘텀 시그널 생성")
        signal_df = self.generate_signal(data)
        buy_signals = signal_df[signal_df["signal"] == STRATEGY_SIGNAL.BUY]
        logger.info(f"[{self.__class__.__name__}] BUY 시그널: {len(buy_signals)}종목")
        
        # ── 4단계: TradeIntent 변환 ──
        orders = self._build_trade_intents(
            buy_signals=buy_signals,
            signal_df=signal_df,
            data=data,
            name_map=name_map,
        )
        
        return StrategyResult(
            strategy_type=self.strategy_type,
            strategy_name=self.__class__.__name__,
            orders=orders,
            metadata={
                "universe_count": len(df_universe),
                "ohlcv_loaded": len(data),
                "signal_buy_count": len(buy_signals),
                "year": year,
            },
        )
    
    
    # ⚙️ Private helpers
    def _load_ohlcv(self, stock_codes: list[str]) -> dict[str, pd.DataFrame]:
        """유니버스 종목의 OHLCV 데이터 로딩"""
        today = pd.Timestamp.today().strftime("%Y-%m-%d")
        lookback_start = (
            pd.Timestamp.today()
            - pd.tseries.offsets.BDay(self.momentum.lookback_days + 30)
        ).strftime("%Y-%m-%d")
        
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
        
        return data
    
    
    # ⚙️ TradeIntent 변환 로직
    def _build_trade_intents(
        self,
        buy_signals: pd.DataFrame,
        signal_df: pd.DataFrame,
        data: dict[str, pd.DataFrame],
        name_map: dict[str, str],
    ) -> list[TradeIntent]:
        """BUY 시그널을 균등 비중 TradeIntent 리스트로 변환"""
        buy_count = len(buy_signals)
        if buy_count == 0:
            return []
        
        orders = []
        for code in buy_signals.index:
            # 현재가 조회
            price = None
            if code in data and not data[code].empty:
                price = int(data[code]["Close"].iloc[-1])
            
            orders.append(
                TradeIntent(
                    stock_code=code,
                    stock_name=name_map.get(code, code),
                    side=TradeSide.BUY,
                    weight=1.0 / buy_count,
                    price_hint=price,
                    reason=(
                        f"f_score>=threshold, "
                        f"momentum_rank={int(signal_df.loc[code, 'rank'])}"
                    ),
                    metadata={
                        "momentum_return": float(signal_df.loc[code, "return"]),
                        "momentum_rank": int(signal_df.loc[code, "rank"]),
                    },
                )
            )
        
        return orders