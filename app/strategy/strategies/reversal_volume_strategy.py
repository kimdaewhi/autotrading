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

⭐ DirectTradeStrategy 인터페이스 (Executor 연동)
    - should_exit()            : TP/SL/시간 청산 판정
    - generate_entry_signals() : scan_from_data + 쿨다운/기보유 필터
    - size_position()          : 균등 분할 사이징

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
# ── 변경: BaseStrategy → DirectTradeStrategy 상속 ──
from app.strategy.strategies.direct_trade_strategy import DirectTradeStrategy
from app.core.strategy_settings import strategy_settings
from app.core.settings import settings
from app.schemas.strategy.trading import (
    StrategyType,
    StrategyResult,
    TradeIntent,
    TradeSide,
    # ── 추가: Executor 연동용 ──
    ExitDecision,
    ExitReason,
)
# ── 추가: 시뮬레이션 런타임 객체 ──
from app.schemas.strategy.simulation import SwingPosition, SwingTradeRecord
from app.strategy.universe.blacklist import SPECIAL_ENTITY_CODES


logger = logging.getLogger(__name__)


class ReversalVolumeStrategy(DirectTradeStrategy):
    """
    Short-term Reversal + Volume 스윙 전략
    
    ⭐ 실행 흐름
        실전:    scan() → execute() → DirectTradeExecutor (향후)
        백테스트: generate_entry_signals() / should_exit() → BacktestExecutor
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
    
    
    # ⚙️ 1단계: 유동성 필터 (실전/백테스트 공용)
    def _filter_liquidity(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        1단계 — 유동성 필터 (공용: 실전/백테스트)
        
        거래 가능한 종목 중 충분한 유동성을 확보한 상위 N개를 선정한다.
        슬리피지 부담이 큰 소형주를 사전에 배제하여 실전 체결 가능성을 담보한다.
        
        ⭐ 필터링 단계 (순차 적용)
            1. 시가총액 하한 (RV_MIN_MARCAP, 기본 5천억)
                → "규모" 기준: 조작/소형주 리스크 배제
            2. 보통주 종목코드 정제 (6자리 숫자 + 끝자리 0)
            3. 거래소 필터 (KOSPI/KOSDAQ/KOSDAQ GLOBAL)
            4. 특수 엔티티 블랙리스트 제외 (인프라펀드, 리츠 등)
            5. 평균 거래대금 상위 RV_TOP_N_LIQUID개 선정 (기본 200)
                → "체결성" 기준: 시총이 커도 거래가 얇은 종목(지주사, 대주주 지분
                    집중 종목) 배제. 실측상 시총 5천억 이상 575개 중 330개가 이 단계
                    에서 탈락 → 두 필터가 독립적으로 유의미하게 작동.
        
        ⚠️ 알려진 제약
            - `get_stock_list_raw(as_of_date=None)`: 현재 시점의 상장 리스트를 사용.
            백테스트 시 생존자 편향(survivorship bias) 가능성 있음.
            → 향후 과거 시점 상장 리스트 지원 시 교체 필요.
            - 평균 거래대금은 전체 [start_date, end_date] 구간을 사용.
            백테스트 시작 시점에서 미래 거래대금을 알 수 없음에도 참조하는
            look-ahead 소지 있음 → 향후 rolling window 기반으로 개선 고려.
        """
        s = strategy_settings
        
        # 소형주 배제: 체결 슬리피지 및 조작 리스크 방지
        df_list = self.data_provider.get_stock_list_raw(as_of_date=None)
        df_list = df_list[df_list["Marcap"] >= s.RV_MIN_MARCAP]
        
        # 보통주 필터
        df_list = df_list[df_list["Code"].str.match(r"^\d{6}$")]    # 6자리 숫자 코드만 (ETF, 리츠 등 제외)
        df_list = df_list[df_list["Code"].str[-1] == "0"]           # 보통주만 (보통주 끝자리 0, 우선주 5)
        
        # 거래소 필터
        df_list = df_list[df_list["Market"].isin(["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"])]
        
        # 특수 엔티티 필터
        df_list = df_list[~df_list["Code"].isin(SPECIAL_ENTITY_CODES)]
        
        # 평균 거래대금 산출
        # 시총이 커도 실제 거래가 얇으면 체결이 어려움
        avg_amounts = {}
        for code in df_list["Code"]:
            try:
                df_ohlcv = self.data_provider.get_ohlcv(code, start_date, end_date)
                if len(df_ohlcv) >= s.RV_AVG_AMOUNT_DAYS:
                    recent = df_ohlcv.tail(s.RV_AVG_AMOUNT_DAYS)
                    # TODO(P2/백테스트): 절대 평균 거래대금 → 상대적 랭킹으로 개선 고려 (look-ahead 방지)
                    avg_amounts[code] = (recent["Close"] * recent["Volume"]).mean()
            except Exception:
                continue
        
        # 거래대금 기준 상위 N개 종목 선별
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
            df_slice = preloaded_data[code][preloaded_data[code].index <= scan_date]    # scan_date까지의 데이터 슬라이스
            
            # 과거 N일 데이터가 충분하지 않으면 스킵 (look-ahead 방지)
            if len(df_slice) < s.RV_REVERSAL_DAYS + 1:
                continue
            
            # 최근 N일 수익률 계산(가장 최근 종가 vs N일 전 종가)
            returns[code] = (df_slice["Close"].iloc[-1] / df_slice["Close"].iloc[-(s.RV_REVERSAL_DAYS + 1)]) - 1
        
        if not returns:
            return pd.DataFrame()
        
        df = df_universe[df_universe["Code"].isin(returns.keys())].copy()
        df["return_pct"] = df["Code"].map(returns)      # 수익률 매핑
        
        # 과매도 종목 필터링 (음수 수익률)
        df = df[df["return_pct"] < 0]
        if df.empty:
            return pd.DataFrame()
        
        # 수익률 컷오프를 통한 리스크 관리 (과매도 종목 중에서도 낙폭이 큰 종목 선별)
        cutoff = max(1, int(len(df) * s.RV_REVERSAL_PCT))
        df = df.sort_values("return_pct").head(cutoff)
        
        # ── 3단계: Volume Spike 판단 ──
        ratios = {}
        for code in df["Code"]:
            if code not in preloaded_data:
                continue
            
            df_slice = preloaded_data[code][preloaded_data[code].index <= scan_date]
            if len(df_slice) < s.RV_VOLUME_AVG_DAYS + 1:
                continue
            cur = df_slice["Volume"].iloc[-1]
            
            # 과거 N일 평균 거래량 계산 (scan_date 이전 데이터만 사용, look-ahead 방지)
            avg = df_slice["Volume"].iloc[-(s.RV_VOLUME_AVG_DAYS + 1):-1].mean()
            if avg > 0:
                ratios[code] = cur / avg
        
        if not ratios:
            return pd.DataFrame()
        
        df = df[df["Code"].isin(ratios.keys())].copy()          # Volume spike 계산 가능 종목
        df["volume_ratio"] = df["Code"].map(ratios)
        df = df[df["volume_ratio"] >= s.RV_VOLUME_SPIKE_RATIO]  # Volume spike 기준 충족 종목
        
        if df.empty:
            return pd.DataFrame()
        
        return self._apply_risk_cut(df).sort_values("return_pct")
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DirectTradeStrategy 인터페이스 구현
    # Executor(백테스트/실매매)가 호출하는 진입/청산/사이징 메서드
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ⚙️ 청산 판정
    def should_exit(
        self,
        position: SwingPosition,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
    ) -> ExitDecision:
        """
        포지션 청산 여부 판정.
        
        우선순위 (먼저 충족되는 조건으로 청산):
            1. 익절: ret >= RV_TAKE_PROFIT_PCT
            2. 손절: ret <= RV_STOP_LOSS_PCT
            3. 시간 청산: holding_days >= RV_MAX_HOLDING_DAYS
        
        ⚠️ holding_days 증가는 Executor 책임. 본 메서드는 position.holding_days를
           그대로 읽기만 함. Executor는 should_exit 호출 전에 +1 해야 함.
        """
        s = strategy_settings
        
        # 데이터 없으면 청산 불가 (보유 유지)
        if position.stock_code not in data or date not in data[position.stock_code].index:
            return ExitDecision(should_exit=False)
        
        price = data[position.stock_code].loc[date, "Close"]
        ret = (price - position.entry_price) / position.entry_price
        
        if ret >= s.RV_TAKE_PROFIT_PCT:
            return ExitDecision(should_exit=True, reason=ExitReason.TAKE_PROFIT)
        elif ret <= s.RV_STOP_LOSS_PCT:
            return ExitDecision(should_exit=True, reason=ExitReason.STOP_LOSS)
        elif position.holding_days >= s.RV_MAX_HOLDING_DAYS:
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
    ) -> pd.DataFrame:
        """
        순수 시그널 계산(scan_from_data) + 전략 고유 필터를 모두 적용한
        최종 진입 후보를 반환한다.
        
        필터 단계:
            1. scan_from_data(): 과매도 + 볼륨 스파이크 + 급락 컷
            2. 기보유 종목 제외
            3. 쿨다운 기간 내 재청산 종목 제외
        
        ⚠️ recent_trade_history는 Executor가 미리 잘라서 전달.
           Executor 측에서 충분히 긴 윈도우로 넘겨주면 됨 (기본: 쿨다운 * 2 or 30일).
        
        ⚠️ 쿨다운은 캘린더 일수 기준 (영업일 아님). 기존 Executor 로직과 동일하게
           유지. 영업일 기준 전환은 Step 3 개선 대상.
        """
        s = strategy_settings
        
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
            if (date - t.exit_date).days <= s.RV_COOLDOWN_DAYS
        }
        
        # 쿨다운 진단 로그 (블록된 종목이 있을 때만)
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
        단일 시그널에 배분할 주문 금액 산정.
        
        ⚠️ 현재 구현: 가용 현금을 신규 진입 종목 수로 균등 분할.
           기존 Executor의 `alloc = cash / len(candidates)` 로직을 그대로 이식.
        
        ⚠️ 알려진 이슈 (Step 3 개선 대상)
           - 이미 보유 포지션이 있을 때 남은 현금을 소수 신규 진입에 몰아 넣는 편향
           - 예: 3개 기보유 + 1개 신규 진입 → 남은 현금 전체가 1개 종목에 집중
           - 개선 방향: total_equity / RV_MAX_POSITIONS 기반 고정 비중 방식 등 검토
        """
        if num_new_entries <= 0:
            return 0.0
        return available_cash / num_new_entries
    
    
    # ⚙️ BaseSignal 호환
    def generate_signal(self, stock_codes, data, **kwargs):
        return self.scan(scan_date=kwargs.get("scan_date"))