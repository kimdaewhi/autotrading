"""
Short-term Reversal + Volume 스윙 전략

⭐ 전략 컨셉
    단기 과매도 종목 중 거래량 급증으로 바닥 신호가 나타난 종목에 진입,
    평균 회귀(Mean Reversion) 반등을 2~5영업일 내 수익화하는 스윙 전략.

⭐ 파이프라인 (4단계)
    1. Liquidity Filter  — 유동성 충분한 종목만 대상 (거래대금 기준)
    2. Reversal Screen   — 최근 N일 수익률 하위 X% 선별 (과매도 종목)
    3. Volume Spike       — 거래량 급증 확인 (바닥 신호)
    4. Risk Cut           — 과도 급락 종목 제거 (지하실 리스크 방지)

⭐ 청산 규칙 (먼저 충족되는 조건으로 청산)
    - 익절: 목표 수익률 도달 시
    - 손절: 손절선 도달 시
    - 시간 청산: 최대 보유일 초과 시

⭐ 포지셔닝
    - Core 전략(F-Score + Momentum)의 Satellite 전략
    - Core가 약한 횡보/테마장에서 보완 역할
    - 재무 데이터 불필요, OHLCV만으로 동작

⚠️ 알려진 리스크
    - 낙폭 과대 종목이 추가 하락할 수 있음 (falling knife)
    - Volume spike가 악재성 매도일 수 있음 (바닥이 아니라 붕괴)
    - Risk cut과 손절선으로 방어하되, 완전한 방어는 불가
"""
import logging

import pandas as pd

from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.strategies.base_strategy import BaseStrategy
from app.core.strategy_settings import strategy_settings
from app.schemas.strategy.trading import (
    StrategyType,
    StrategyResult,
    TradeIntent,
    TradeSide,
)


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 전략 클래스
# ──────────────────────────────────────────────
class ReversalVolumeStrategy(BaseStrategy):
    """
    Short-term Reversal + Volume 스윙 전략
    
    ⭐ 실행 흐름
        1. scan() — 매일 장 마감 후 호출, 진입 후보 종목 반환
        2. execute() — scan 결과를 TradeIntent로 변환
        3. Executor — TradeIntent를 받아 실제 주문 실행 (향후 DirectTradeExecutor)
    
    ⭐ 기존 시스템과의 차이
        - F-Score+Momentum: 월 1회, 재무제표 기반, RebalanceExecutor
        - Reversal+Volume: 매일, OHLCV 기반, DirectTradeExecutor (향후)
    """
    
    def __init__(
        self,
        data_provider: FDRMarketDataProvider | None = None,
    ):
        self.data_provider = data_provider or FDRMarketDataProvider()
    
    
    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.DIRECT_TRADE
    
    
    @property
    def strategy_name(self) -> str:
        return "ReversalVolume"
    
    
    # ⚙️ 전략 전체 파이프라인 실행
    async def execute(self, **kwargs) -> StrategyResult:
        """
        전략 실행 엔트리포인트
        
        Parameters (kwargs)
        ----------
        scan_date : str
            스캔 기준일 (YYYY-MM-DD). None이면 오늘 날짜.
        current_positions : list[str]
            현재 보유 중인 종목 코드 리스트 (중복 진입 방지)
        """
        scan_date = kwargs.get("scan_date", None)
        current_positions = kwargs.get("current_positions", [])
        
        # 1. 스캔 — 진입 후보 종목 선별
        candidates = self.scan(scan_date=scan_date)
        
        # 2. 기보유 종목 제외
        candidates = candidates[~candidates["Code"].isin(current_positions)]
        
        # 3. 최대 포지션 제한
        available_slots = strategy_settings.RV_MAX_POSITIONS - len(current_positions)
        if available_slots <= 0:
            logger.info("[ReversalVolume] 최대 포지션 도달, 신규 진입 없음")
            candidates = candidates.head(0)
        else:
            candidates = candidates.head(available_slots)
        
        # 4. TradeIntent 변환
        intents = []
        for _, row in candidates.iterrows():
            intents.append(TradeIntent(
                code=row["Code"],
                name=row["Name"],
                direction=TradeSide.BUY,
                reason=(
                    f"Reversal {row['return_pct']:.1%} / "
                    f"Volume spike {row['volume_ratio']:.1f}x"
                ),
            ))
        
        logger.info(
            f"[ReversalVolume] scan_date={scan_date} → "
            f"후보 {len(candidates)}개 → TradeIntent {len(intents)}개"
        )
        
        return StrategyResult(
            strategy_name=self.strategy_name,
            strategy_type=self.strategy_type,
            intents=intents,
            metadata={
                "scan_date": scan_date,
                "candidates_count": len(candidates),
            },
        )
    
    
    # ⚙️ 매일 장 마감 후 스캔 — 진입 후보 종목 선별
    def scan(self, scan_date: str | None = None) -> pd.DataFrame:
        """
        4단계 파이프라인을 거쳐 진입 후보 종목을 반환
        
        Parameters
        ----------
        scan_date : str | None
            스캔 기준일 (YYYY-MM-DD). None이면 가장 최근 영업일.
        
        Returns
        -------
        pd.DataFrame
            진입 후보 종목 (columns: Code, Name, return_pct, volume_ratio, ...)
            return_pct 오름차순 (가장 많이 빠진 종목이 상위)
        """
        s = strategy_settings
        
        # ── OHLCV 데이터 로딩에 필요한 기간 산출 ──
        # reversal_days와 volume_avg_days 중 긴 쪽 + 여유분
        lookback = max(s.RV_REVERSAL_DAYS, s.RV_AVG_AMOUNT_DAYS, s.RV_VOLUME_AVG_DAYS) + 10
        
        if scan_date:
            end_date = scan_date
        else:
            end_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        
        start_date = (
            pd.to_datetime(end_date) - pd.tseries.offsets.BDay(lookback)
        ).strftime("%Y-%m-%d")
        
        logger.info(f"[ReversalVolume] 스캔 시작: {end_date} (lookback={lookback}일)")
        
        # ── 1단계: Liquidity Filter ──
        df_universe = self._filter_liquidity(start_date, end_date)
        logger.info(f"[ReversalVolume] 1단계 Liquidity → {len(df_universe)}개 종목")
        
        if df_universe.empty:
            return pd.DataFrame()
        
        # ── 2단계: Reversal Screen ──
        df_reversal = self._screen_reversal(df_universe, start_date, end_date)
        logger.info(f"[ReversalVolume] 2단계 Reversal → {len(df_reversal)}개 종목")
        
        if df_reversal.empty:
            return pd.DataFrame()
        
        # ── 3단계: Volume Spike ──
        df_volume = self._check_volume_spike(df_reversal, start_date, end_date)
        logger.info(f"[ReversalVolume] 3단계 Volume Spike → {len(df_volume)}개 종목")
        
        if df_volume.empty:
            return pd.DataFrame()
        
        # ── 4단계: Risk Cut ──
        df_final = self._apply_risk_cut(df_volume)
        logger.info(f"[ReversalVolume] 4단계 Risk Cut → {len(df_final)}개 종목 (최종)")
        
        return df_final.sort_values("return_pct", ascending=True)
    
    
    # ⚙️ 1단계: 유동성 필터 — 거래대금 상위 N개 종목 선별
    def _filter_liquidity(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        최근 RV_AVG_AMOUNT_DAYS일 평균 거래대금 기준 상위 RV_TOP_N_LIQUID개 선별
        시총 하한(RV_MIN_MARCAP) 미만 종목 제외
        """
        s = strategy_settings
        
        # 현재 상장 종목 리스트
        df_list = self.data_provider.get_stock_list_raw(as_of_date=None)
        
        # 시총 필터
        df_list = df_list[df_list["Marcap"] >= s.RV_MIN_MARCAP]
        
        # 기본 필터 (특수종목, 우선주, ETF 제외)
        df_list = df_list[df_list["Code"].str.match(r"^\d{6}$")]
        df_list = df_list[df_list["Code"].str[-1] == "0"]
        df_list = df_list[df_list["Market"].isin(["KOSPI", "KOSDAQ"])]
        
        # 각 종목의 평균 거래대금 산출
        avg_amounts = {}
        for code in df_list["Code"]:
            try:
                df_ohlcv = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df_ohlcv) >= s.RV_AVG_AMOUNT_DAYS:
                    # 최근 RV_AVG_AMOUNT_DAYS일의 평균 거래대금
                    recent = df_ohlcv.tail(s.RV_AVG_AMOUNT_DAYS)
                    avg_amount = (recent["Close"] * recent["Volume"]).mean()
                    avg_amounts[code] = avg_amount
            except Exception:
                continue
        
        # 거래대금 상위 N개 선별
        df_list = df_list[df_list["Code"].isin(avg_amounts.keys())].copy()
        df_list["AvgAmount"] = df_list["Code"].map(avg_amounts)
        df_list = df_list.sort_values("AvgAmount", ascending=False).head(s.RV_TOP_N_LIQUID)
        
        return df_list
    
    
    # ⚙️ 2단계: 단기 역추세 스크리닝 — 최근 N일 수익률 하위 X%
    def _screen_reversal(
        self, df_universe: pd.DataFrame, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        최근 RV_REVERSAL_DAYS일 수익률을 계산하고, 하위 RV_REVERSAL_PCT 비율만 선별
        """
        s = strategy_settings
        
        returns = {}
        for code in df_universe["Code"]:
            try:
                df_ohlcv = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df_ohlcv) < s.RV_REVERSAL_DAYS + 1:
                    continue
                
                # 최근 RV_REVERSAL_DAYS일 수익률
                close_now = df_ohlcv["Close"].iloc[-1]
                close_before = df_ohlcv["Close"].iloc[-(s.RV_REVERSAL_DAYS + 1)]
                ret = (close_now - close_before) / close_before
                returns[code] = ret
            except Exception:
                continue
        
        if not returns:
            return pd.DataFrame()
        
        # 하위 X% 선별
        df_universe = df_universe[df_universe["Code"].isin(returns.keys())].copy()
        df_universe["return_pct"] = df_universe["Code"].map(returns)
        
        # 음수 수익률(하락 종목)만 대상
        df_universe = df_universe[df_universe["return_pct"] < 0]
        
        # 하위 RV_REVERSAL_PCT 비율 컷오프
        cutoff_count = max(1, int(len(df_universe) * s.RV_REVERSAL_PCT))
        df_universe = df_universe.sort_values("return_pct", ascending=True).head(cutoff_count)
        
        return df_universe
    
    
    # ⚙️ 3단계: 거래량 급증 확인 — 바닥 신호 감지
    def _check_volume_spike(
        self, df_reversal: pd.DataFrame, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        당일 거래량이 최근 RV_VOLUME_AVG_DAYS일 평균 대비 RV_VOLUME_SPIKE_RATIO배 이상인 종목만 통과
        """
        s = strategy_settings
        
        volume_ratios = {}
        for code in df_reversal["Code"]:
            try:
                df_ohlcv = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df_ohlcv) < s.RV_VOLUME_AVG_DAYS + 1:
                    continue
                
                # 당일 거래량 vs 최근 N일 평균 거래량
                current_volume = df_ohlcv["Volume"].iloc[-1]
                avg_volume = df_ohlcv["Volume"].iloc[-(s.RV_VOLUME_AVG_DAYS + 1):-1].mean()
                
                if avg_volume > 0:
                    ratio = current_volume / avg_volume
                    volume_ratios[code] = ratio
            except Exception:
                continue
        
        if not volume_ratios:
            return pd.DataFrame()
        
        # spike ratio 이상만 통과
        df_reversal = df_reversal[df_reversal["Code"].isin(volume_ratios.keys())].copy()
        df_reversal["volume_ratio"] = df_reversal["Code"].map(volume_ratios)
        df_reversal = df_reversal[df_reversal["volume_ratio"] >= s.RV_VOLUME_SPIKE_RATIO]
        
        return df_reversal
    
    
    # ⚙️ 4단계: 리스크 컷 — 과도 급락 종목 제거
    def _apply_risk_cut(self, df_candidates: pd.DataFrame) -> pd.DataFrame:
        """
        기간 내 낙폭이 RV_MAX_DRAWDOWN_PCT 이하인 종목 제외 (falling knife 방지)
        """
        s = strategy_settings
        
        # return_pct가 RV_MAX_DRAWDOWN_PCT보다 더 빠진 종목 제거
        df_filtered = df_candidates[df_candidates["return_pct"] > s.RV_MAX_DRAWDOWN_PCT]
        
        return df_filtered
    
    
    # ⚙️ 시그널 생성 (BaseSignal 인터페이스 호환용)
    def generate_signal(self, stock_codes: list[str], data: dict, **kwargs) -> pd.DataFrame:
        """
        BaseSignal 인터페이스 호환
        Reversal+Volume 전략은 scan()이 메인이므로, 
        백테스트 러너 연동 시 이 메서드를 통해 호출
        """
        scan_date = kwargs.get("scan_date", None)
        candidates = self.scan(scan_date=scan_date)
        return candidates