"""
Short-term Reversal + Volume 스윙 전략
(기존 docstring 유지)
"""
import logging

import pandas as pd

from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.market.provider.dart_provider import _load_stock_name_map
from app.strategy.strategies.direct_trade_strategy import DirectTradeStrategy
from app.core.settings_strategy import strategy_settings
from app.core.settings import settings
from app.schemas.strategy.trading import (
    StrategyType,
    StrategyResult,
    TradeIntent,
    TradeSide,
    ExitDecision,
    ExitReason,
)
from app.schemas.strategy.simulation import SwingPosition, SwingTradeRecord
from app.strategy.universe.blacklist import SPECIAL_ENTITY_CODES


logger = logging.getLogger(__name__)


class ReversalVolumeStrategy(DirectTradeStrategy):
    """
    Short-term Reversal + Volume 스윙 전략
    
    ⭐ 실행 흐름
        실전:    scan() → execute() → DirectTradeExecutor (향후)
        백테스트: generate_entry_signals() / should_exit() → BacktestExecutor
    
    ⭐ 파라미터 주입
        모든 RV_* 파라미터를 생성자에서 주입 가능. None 전달 시 strategy_settings
        기본값 사용. 민감도 테스트 시 특정 파라미터만 오버라이드하여 스윕 가능.
        
        예시:
            # 실매매: 기본값 그대로 사용
            strategy = ReversalVolumeStrategy(provider)
            
            # 백테스트 스윕: volume_spike_ratio만 변경
            strategy = ReversalVolumeStrategy(
                provider, volume_spike_ratio=1.5
            )
    """
    
    def __init__(
        self,
        data_provider: FDRMarketDataProvider | None = None,
        # ── 1단계: Liquidity Filter ──
        max_marcap: float | None = None,
        min_marcap: float | None = None,
        avg_amount_days: int | None = None,
        top_n_liquid: int | None = None,
        # ── 2단계: Reversal Screen ──
        reversal_days: int | None = None,
        reversal_pct: float | None = None,
        # ── 3단계: Volume Spike ──
        volume_avg_days: int | None = None,
        volume_spike_ratio: float | None = None,
        # ── 4단계: Risk Cut ──
        max_drawdown_pct: float | None = None,
        # ── 청산 규칙 ──
        take_profit_pct: float | None = None,
        stop_loss_pct: float | None = None,
        max_holding_days: int | None = None,
        # ── 포트폴리오 ──
        max_positions: int | None = None,
        # ── 시장 필터 ──
        market_filter_enabled: bool | None = None,
        market_ma_days: int | None = None,
        # ── 쿨다운 ──
        cooldown_days: int | None = None,
    ):
        self.data_provider = data_provider or FDRMarketDataProvider()
        
        s = strategy_settings
        
        # 1단계: Liquidity Filter
        self.max_marcap = max_marcap if max_marcap is not None else s.RV_MAX_MARCAP
        self.min_marcap = min_marcap if min_marcap is not None else s.RV_MIN_MARCAP
        self.avg_amount_days = avg_amount_days if avg_amount_days is not None else s.RV_AVG_AMOUNT_DAYS
        self.top_n_liquid = top_n_liquid if top_n_liquid is not None else s.RV_TOP_N_LIQUID
        
        # 2단계: Reversal Screen
        self.reversal_days = reversal_days if reversal_days is not None else s.RV_REVERSAL_DAYS
        self.reversal_pct = reversal_pct if reversal_pct is not None else s.RV_REVERSAL_PCT
        
        # 3단계: Volume Spike
        self.volume_avg_days = volume_avg_days if volume_avg_days is not None else s.RV_VOLUME_AVG_DAYS
        self.volume_spike_ratio = volume_spike_ratio if volume_spike_ratio is not None else s.RV_VOLUME_SPIKE_RATIO
        
        # 4단계: Risk Cut
        self.max_drawdown_pct = max_drawdown_pct if max_drawdown_pct is not None else s.RV_MAX_DRAWDOWN_PCT
        
        # 청산 규칙
        self.take_profit_pct = take_profit_pct if take_profit_pct is not None else s.RV_TAKE_PROFIT_PCT
        self.stop_loss_pct = stop_loss_pct if stop_loss_pct is not None else s.RV_STOP_LOSS_PCT
        self.max_holding_days = max_holding_days if max_holding_days is not None else s.RV_MAX_HOLDING_DAYS
        
        # 포트폴리오
        self.max_positions = max_positions if max_positions is not None else s.RV_MAX_POSITIONS
        
        # 시장 필터
        self.market_filter_enabled = market_filter_enabled if market_filter_enabled is not None else s.RV_MARKET_FILTER_ENABLED
        self.market_ma_days = market_ma_days if market_ma_days is not None else s.RV_MARKET_MA_DAYS
        
        # 쿨다운
        self.cooldown_days = cooldown_days if cooldown_days is not None else s.RV_COOLDOWN_DAYS
    
    
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
        
        available_slots = self.max_positions - len(current_positions)
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
        lookback = max(self.reversal_days, self.avg_amount_days, self.volume_avg_days) + 10
        
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
    
    
    # ⚙️ 1단계: 유동성 필터 (실전/백테스트 공용)
    def _filter_liquidity(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        1단계 — 유동성 필터 (공용: 실전/백테스트)
        (기존 docstring 유지)
        """
        # 소형주 배제
        df_list = self.data_provider.get_stock_list_raw(as_of_date=None)
        df_list = df_list[df_list["Marcap"] >= self.min_marcap]
        df_list = df_list[df_list["Marcap"] <= self.max_marcap]
        
        # 보통주 필터
        df_list = df_list[df_list["Code"].str.match(r"^\d{6}$")]
        df_list = df_list[df_list["Code"].str[-1] == "0"]
        
        # 거래소 필터
        df_list = df_list[df_list["Market"].isin(["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"])]
        
        # 특수 엔티티 필터
        df_list = df_list[~df_list["Code"].isin(SPECIAL_ENTITY_CODES)]
        
        # 평균 거래대금 산출
        avg_amounts = {}
        for code in df_list["Code"]:
            try:
                df_ohlcv = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df_ohlcv) >= self.avg_amount_days:
                    recent = df_ohlcv.tail(self.avg_amount_days)
                    avg_amounts[code] = (recent["Close"] * recent["Volume"]).mean()
            except Exception:
                continue
        
        # 거래대금 기준 상위 N개 선별
        df_list = df_list[df_list["Code"].isin(avg_amounts.keys())].copy()
        df_list["AvgAmount"] = df_list["Code"].map(avg_amounts)
        return df_list.sort_values("AvgAmount", ascending=False).head(self.top_n_liquid)
    
    
    # ⚙️ 2단계: Reversal (실전용)
    def _screen_reversal(self, df_universe, start_date, end_date):
        returns = {}
        for code in df_universe["Code"]:
            try:
                df = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df) < self.reversal_days + 1:
                    continue
                returns[code] = (df["Close"].iloc[-1] / df["Close"].iloc[-(self.reversal_days + 1)]) - 1
            except Exception:
                continue
        if not returns:
            return pd.DataFrame()
        df = df_universe[df_universe["Code"].isin(returns.keys())].copy()
        df["return_pct"] = df["Code"].map(returns)
        df = df[df["return_pct"] < 0]
        cutoff = max(1, int(len(df) * self.reversal_pct))
        return df.sort_values("return_pct").head(cutoff)
    
    
    # ⚙️ 3단계: Volume Spike (실전용)
    def _check_volume_spike(self, df_reversal, start_date, end_date):
        ratios = {}
        for code in df_reversal["Code"]:
            try:
                df = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df) < self.volume_avg_days + 1:
                    continue
                cur = df["Volume"].iloc[-1]
                avg = df["Volume"].iloc[-(self.volume_avg_days + 1):-1].mean()
                if avg > 0:
                    ratios[code] = cur / avg
            except Exception:
                continue
        if not ratios:
            return pd.DataFrame()
        df = df_reversal[df_reversal["Code"].isin(ratios.keys())].copy()
        df["volume_ratio"] = df["Code"].map(ratios)
        return df[df["volume_ratio"] >= self.volume_spike_ratio]
    
    
    # ⚙️ 4단계: 리스크 컷 (공용)
    def _apply_risk_cut(self, df):
        return df[df["return_pct"] > self.max_drawdown_pct]
    
    
    # ⚙️ 시장 국면 체크 (공용)
    def _is_bear_market(self, date: pd.Timestamp, df_benchmark: pd.DataFrame | None) -> bool:
        """
        시장 국면 판정: KOSPI 종가가 N일 이동평균 아래면 하락장으로 판단
        
        Returns
        -------
        bool: True면 하락장(진입 허용), False면 상승장(진입 차단)
        """
        if df_benchmark is None or df_benchmark.empty:
            return True  # 데이터 없으면 안전하게 진입 허용 (필터 없는 셈)
        
        # date까지 슬라이스
        df_slice = df_benchmark[df_benchmark.index <= date]
        
        if len(df_slice) < self.market_ma_days + 1:
            return True  # 이평 계산 데이터 부족
        
        current_close = df_slice["Close"].iloc[-1]
        ma = df_slice["Close"].iloc[-self.market_ma_days:].mean()
        
        return current_close < ma  # 종가 < 이평 → 하락장
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 백테스트용: 사전 로딩
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ⚙️ 백테스트용 유니버스 구성 (1번만 호출)
    def build_universe(self, start: str, end: str) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
        """
        유니버스 선정 + OHLCV 사전 로딩 + DART 종목명 매핑
        """
        lookback = max(self.reversal_days, self.avg_amount_days, self.volume_avg_days) + 10
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
        # ── 2단계: Reversal ──
        returns = {}
        for code in df_universe["Code"]:
            if code not in preloaded_data:
                continue
            df_slice = preloaded_data[code][preloaded_data[code].index <= scan_date]
            
            if len(df_slice) < self.reversal_days + 1:
                continue
            
            returns[code] = (df_slice["Close"].iloc[-1] / df_slice["Close"].iloc[-(self.reversal_days + 1)]) - 1
        
        if not returns:
            return pd.DataFrame()
        
        df = df_universe[df_universe["Code"].isin(returns.keys())].copy()
        df["return_pct"] = df["Code"].map(returns)
        
        df = df[df["return_pct"] < 0]
        if df.empty:
            return pd.DataFrame()
        
        cutoff = max(1, int(len(df) * self.reversal_pct))
        df = df.sort_values("return_pct").head(cutoff)
        
        # ── 3단계: Volume Spike ──
        ratios = {}
        for code in df["Code"]:
            if code not in preloaded_data:
                continue
            
            df_slice = preloaded_data[code][preloaded_data[code].index <= scan_date]
            if len(df_slice) < self.volume_avg_days + 1:
                continue
            cur = df_slice["Volume"].iloc[-1]
            
            avg = df_slice["Volume"].iloc[-(self.volume_avg_days + 1):-1].mean()
            if avg > 0:
                ratios[code] = cur / avg
        
        if not ratios:
            return pd.DataFrame()
        
        df = df[df["Code"].isin(ratios.keys())].copy()
        df["volume_ratio"] = df["Code"].map(ratios)
        df = df[df["volume_ratio"] >= self.volume_spike_ratio]
        
        if df.empty:
            return pd.DataFrame()
        
        return self._apply_risk_cut(df).sort_values("return_pct")
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DirectTradeStrategy 인터페이스 구현
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ⚙️ 청산 판정
    def should_exit(
        self,
        position: SwingPosition,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
    ) -> ExitDecision:
        """
        (기존 docstring 유지)
        """
        if position.stock_code not in data or date not in data[position.stock_code].index:
            return ExitDecision(should_exit=False)
        
        price = data[position.stock_code].loc[date, "Close"]
        ret = (price - position.entry_price) / position.entry_price
        
        if ret >= self.take_profit_pct:
            return ExitDecision(should_exit=True, reason=ExitReason.TAKE_PROFIT)
        elif ret <= self.stop_loss_pct:
            return ExitDecision(should_exit=True, reason=ExitReason.STOP_LOSS)
        elif position.holding_days >= self.max_holding_days:
            return ExitDecision(should_exit=True, reason=ExitReason.TIME_EXIT)
        
        return ExitDecision(should_exit=False)
    
    
    # ⚙️ 진입 시그널 생성 (순수 시그널 + 전략 필터)
    def generate_entry_signals(
        self,
        date: pd.Timestamp,
        df_universe: pd.DataFrame,
        preloaded_data: dict[str, pd.DataFrame],
        current_positions: list[SwingPosition],
        recent_trade_history: list[SwingTradeRecord],
        df_benchmark: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        (기존 docstring 유지)
        """
        # 0) 시장 국면 게이트 체크(옵션)
        if self.market_filter_enabled:
            if not self._is_bear_market(date, df_benchmark):
                return pd.DataFrame()
        
        # 1) 순수 시그널 계산
        candidates = self.scan_from_data(date, df_universe, preloaded_data)
        if candidates.empty:
            return candidates
        
        candidates_before = len(candidates)
        
        # 2) 기보유 종목 집합
        held = {p.stock_code for p in current_positions}
        
        # 3) 쿨다운 내 청산 종목 집합
        recent_exits = {
            t.stock_code for t in recent_trade_history
            if (date - t.exit_date).days <= self.cooldown_days
        }
        
        # 쿨다운 진단 로그
        blocked_by_held = set(candidates["Code"]) & held
        blocked_by_cooldown = (set(candidates["Code"]) & recent_exits) - held
        
        if blocked_by_cooldown:
            logger.info(
                f"[COOLDOWN] date={date.date()}, "
                f"candidates={candidates_before}, "
                f"blocked_by_held={len(blocked_by_held)}, "
                f"blocked_by_cooldown={len(blocked_by_cooldown)}, "
                f"cooldown_codes={blocked_by_cooldown}, "
                f"recent_exits_size={len(recent_exits)}"
            )
        
        return candidates[~candidates["Code"].isin(held | recent_exits)]
    
    
    # ⚙️ 포지션 사이징
    def size_position(
        self,
        signal: pd.Series,
        available_cash: float,
        total_equity: float,
        num_new_entries: int,
    ) -> float:
        """
        (기존 docstring 유지)
        """
        if num_new_entries <= 0:
            return 0.0
        return available_cash / num_new_entries
    
    
    # ⚙️ BaseSignal 호환
    def generate_signal(self, stock_codes, data, **kwargs):
        return self.scan(scan_date=kwargs.get("scan_date"))