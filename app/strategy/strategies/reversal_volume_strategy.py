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

⭐ 실행 모드
    - scan()           : 실전용. 매일 장 마감 후 호출, API에서 데이터 조회
    - scan_from_data() : 백테스트용. 사전 로딩된 OHLCV 딕셔너리에서 슬라이싱만

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
from app.market.provider.dart_provider import _load_stock_name_map
from app.strategy.strategies.base_strategy import BaseStrategy
from app.core.strategy_settings import strategy_settings
from app.core.settings import settings
from app.schemas.strategy.trading import (
    StrategyType,
    StrategyResult,
    TradeIntent,
    TradeSide,
)


logger = logging.getLogger(__name__)


class ReversalVolumeStrategy(BaseStrategy):
    """
    Short-term Reversal + Volume 스윙 전략
    
    ⭐ 실행 흐름
        실전:    scan() → execute() → DirectTradeExecutor (향후)
        백테스트: scan_from_data() → BacktestExecutor._run_direct_trade()
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
    
    
    # ⚙️ 전략 전체 파이프라인 실행 (실전용)
    async def execute(self, **kwargs) -> StrategyResult:
        scan_date = kwargs.get("scan_date", None)
        current_positions = kwargs.get("current_positions", [])
        
        candidates = self.scan(scan_date=scan_date)
        candidates = candidates[~candidates["Code"].isin(current_positions)]
        
        available_slots = strategy_settings.RV_MAX_POSITIONS - len(current_positions)
        if available_slots <= 0:
            logger.info("[ReversalVolume] 최대 포지션 도달, 신규 진입 없음")
            candidates = candidates.head(0)
        else:
            candidates = candidates.head(available_slots)
        
        orders = []
        for _, row in candidates.iterrows():
            orders.append(TradeIntent(
                stock_code=row["Code"],
                stock_name=row["Name"],
                side=TradeSide.BUY,
                reason=(
                    f"Reversal {row['return_pct']:.1%} / "
                    f"Volume spike {row['volume_ratio']:.1f}x"
                ),
            ))
        
        return StrategyResult(
            strategy_name=self.strategy_name,
            strategy_type=self.strategy_type,
            orders=orders,
            metadata={"scan_date": scan_date, "candidates_count": len(candidates)},
        )
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 실전용: API에서 데이터 조회
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ⚙️ 실전용 스캔
    def scan(self, scan_date: str | None = None) -> pd.DataFrame:
        s = strategy_settings
        lookback = max(s.RV_REVERSAL_DAYS, s.RV_AVG_AMOUNT_DAYS, s.RV_VOLUME_AVG_DAYS) + 10
        
        end_date = scan_date or pd.Timestamp.now().strftime("%Y-%m-%d")
        start_date = (pd.to_datetime(end_date) - pd.tseries.offsets.BDay(lookback)).strftime("%Y-%m-%d")
        
        df_universe = self._filter_liquidity(start_date, end_date)
        if df_universe.empty:
            return pd.DataFrame()
        
        df_reversal = self._screen_reversal(df_universe, start_date, end_date)
        if df_reversal.empty:
            return pd.DataFrame()
        
        df_volume = self._check_volume_spike(df_reversal, start_date, end_date)
        if df_volume.empty:
            return pd.DataFrame()
        
        return self._apply_risk_cut(df_volume).sort_values("return_pct", ascending=True)
    
    
    # ⚙️ 1단계: 유동성 필터 (실전용)
    def _filter_liquidity(self, start_date: str, end_date: str) -> pd.DataFrame:
        s = strategy_settings
        df_list = self.data_provider.get_stock_list_raw(as_of_date=None)
        df_list = df_list[df_list["Marcap"] >= s.RV_MIN_MARCAP]
        df_list = df_list[df_list["Code"].str.match(r"^\d{6}$")]
        df_list = df_list[df_list["Code"].str[-1] == "0"]
        df_list = df_list[df_list["Market"].isin(["KOSPI", "KOSDAQ"])]
        
        avg_amounts = {}
        for code in df_list["Code"]:
            try:
                df_ohlcv = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df_ohlcv) >= s.RV_AVG_AMOUNT_DAYS:
                    recent = df_ohlcv.tail(s.RV_AVG_AMOUNT_DAYS)
                    avg_amounts[code] = (recent["Close"] * recent["Volume"]).mean()
            except Exception:
                continue
        
        df_list = df_list[df_list["Code"].isin(avg_amounts.keys())].copy()
        df_list["AvgAmount"] = df_list["Code"].map(avg_amounts)
        return df_list.sort_values("AvgAmount", ascending=False).head(s.RV_TOP_N_LIQUID)
    
    
    # ⚙️ 2단계: Reversal (실전용)
    def _screen_reversal(self, df_universe, start_date, end_date):
        s = strategy_settings
        returns = {}
        for code in df_universe["Code"]:
            try:
                df = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df) < s.RV_REVERSAL_DAYS + 1:
                    continue
                returns[code] = (df["Close"].iloc[-1] / df["Close"].iloc[-(s.RV_REVERSAL_DAYS + 1)]) - 1
            except Exception:
                continue
        if not returns:
            return pd.DataFrame()
        df = df_universe[df_universe["Code"].isin(returns.keys())].copy()
        df["return_pct"] = df["Code"].map(returns)
        df = df[df["return_pct"] < 0]
        cutoff = max(1, int(len(df) * s.RV_REVERSAL_PCT))
        return df.sort_values("return_pct").head(cutoff)
    
    
    # ⚙️ 3단계: Volume Spike (실전용)
    def _check_volume_spike(self, df_reversal, start_date, end_date):
        s = strategy_settings
        ratios = {}
        for code in df_reversal["Code"]:
            try:
                df = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df) < s.RV_VOLUME_AVG_DAYS + 1:
                    continue
                cur = df["Volume"].iloc[-1]
                avg = df["Volume"].iloc[-(s.RV_VOLUME_AVG_DAYS + 1):-1].mean()
                if avg > 0:
                    ratios[code] = cur / avg
            except Exception:
                continue
        if not ratios:
            return pd.DataFrame()
        df = df_reversal[df_reversal["Code"].isin(ratios.keys())].copy()
        df["volume_ratio"] = df["Code"].map(ratios)
        return df[df["volume_ratio"] >= s.RV_VOLUME_SPIKE_RATIO]
    
    
    # ⚙️ 4단계: 리스크 컷 (공용)
    def _apply_risk_cut(self, df):
        return df[df["return_pct"] > strategy_settings.RV_MAX_DRAWDOWN_PCT]
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 백테스트용: 사전 로딩
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ⚙️ 백테스트용 유니버스 구성 (1번만 호출)
    def build_universe(self, start: str, end: str) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
        """
        유니버스 선정 + OHLCV 사전 로딩 + DART 종목명 매핑
        """
        s = strategy_settings
        lookback = max(s.RV_REVERSAL_DAYS, s.RV_AVG_AMOUNT_DAYS, s.RV_VOLUME_AVG_DAYS) + 10
        data_start = (pd.to_datetime(start) - pd.tseries.offsets.BDay(lookback)).strftime("%Y-%m-%d")
        
        logger.info(f"[ReversalVolume] 유니버스 구성 시작 ({data_start} ~ {end})")
        
        # 1. 유니버스 선정
        df_universe = self._filter_liquidity(data_start, end)
        
        # 2. DART 종목명 매핑
        name_map = _load_stock_name_map(settings.DART_API_KEY)
        df_universe["Name"] = df_universe["Code"].map(name_map).fillna(df_universe["Code"])
        
        logger.info(f"[ReversalVolume] 유니버스: {len(df_universe)}개 종목")
        
        # 3. OHLCV 사전 로딩
        preloaded_data = {}
        for i, code in enumerate(df_universe["Code"], 1):
            try:
                df_ohlcv = self.data_provider.get_ohlcv(code, data_start, end)
                if not df_ohlcv.empty:
                    df_ohlcv["Date"] = pd.to_datetime(df_ohlcv["Date"])
                    df_ohlcv.set_index("Date", inplace=True)
                    preloaded_data[code] = df_ohlcv
            except Exception:
                continue
            if i % 50 == 0:
                logger.info(f"[ReversalVolume] OHLCV 로딩: {i}/{len(df_universe)}")
        
        logger.info(f"[ReversalVolume] OHLCV 로딩 완료: {len(preloaded_data)}개 종목")
        
        return df_universe, preloaded_data
    
    
    # ⚙️ 백테스트용 스캔 — 사전 로딩 데이터에서 슬라이싱만
    def scan_from_data(self, scan_date, df_universe, preloaded_data):
        s = strategy_settings
        
        # ── 2단계: Reversal ──
        returns = {}
        for code in df_universe["Code"]:
            if code not in preloaded_data:
                continue
            df_slice = preloaded_data[code][preloaded_data[code].index <= scan_date]
            if len(df_slice) < s.RV_REVERSAL_DAYS + 1:
                continue
            returns[code] = (df_slice["Close"].iloc[-1] / df_slice["Close"].iloc[-(s.RV_REVERSAL_DAYS + 1)]) - 1
        
        if not returns:
            return pd.DataFrame()
        
        df = df_universe[df_universe["Code"].isin(returns.keys())].copy()
        df["return_pct"] = df["Code"].map(returns)
        df = df[df["return_pct"] < 0]
        if df.empty:
            return pd.DataFrame()
        
        cutoff = max(1, int(len(df) * s.RV_REVERSAL_PCT))
        df = df.sort_values("return_pct").head(cutoff)
        
        # ── 3단계: Volume Spike ──
        ratios = {}
        for code in df["Code"]:
            if code not in preloaded_data:
                continue
            df_slice = preloaded_data[code][preloaded_data[code].index <= scan_date]
            if len(df_slice) < s.RV_VOLUME_AVG_DAYS + 1:
                continue
            cur = df_slice["Volume"].iloc[-1]
            avg = df_slice["Volume"].iloc[-(s.RV_VOLUME_AVG_DAYS + 1):-1].mean()
            if avg > 0:
                ratios[code] = cur / avg
        
        if not ratios:
            return pd.DataFrame()
        
        df = df[df["Code"].isin(ratios.keys())].copy()
        df["volume_ratio"] = df["Code"].map(ratios)
        df = df[df["volume_ratio"] >= s.RV_VOLUME_SPIKE_RATIO]
        
        if df.empty:
            return pd.DataFrame()
        
        return self._apply_risk_cut(df).sort_values("return_pct")
    
    
    # ⚙️ BaseSignal 호환
    def generate_signal(self, stock_codes, data, **kwargs):
        return self.scan(scan_date=kwargs.get("scan_date"))