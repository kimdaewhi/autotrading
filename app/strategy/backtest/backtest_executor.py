"""
통합 백테스트 실행기

⭐ 역할
    전략의 strategy_type에 따라 적절한 백테스트 로직을 실행하는 통합 실행기.
    실전의 RebalanceExecutor / DirectTradeExecutor 분기와 동일한 구조.

⭐ 분기
    REBALANCE    → 포트폴리오 리밸런싱 (기존 BacktestRunner 로직)
                   주기마다 전체 포트폴리오를 재구성, BUY 종목에 균등 분배
    DIRECT_TRADE → 스윙 개별매매
                   매일 스캔, 종목별 독립 진입/청산 (익절/손절/시간)

⭐ 호출 예시
    executor = BacktestExecutor(strategy, initial_cash=10_000_000)
    result = executor.run(data)
    # result: pd.DataFrame (index=date, columns=equity, cash, holdings_value, ...)
"""
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.schemas.strategy.trading import StrategyType
from app.core.enums import STRATEGY_SIGNAL
from app.core.strategy_settings import strategy_settings


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 스윙 포지션 관리용
# ──────────────────────────────────────────────
@dataclass
class SwingPosition:
    """개별 스윙 포지션 (DIRECT_TRADE용)"""
    code: str
    name: str
    entry_price: float
    quantity: float
    entry_date: pd.Timestamp
    holding_days: int = 0


# ──────────────────────────────────────────────
# 스윙 트레이드 기록용
# ──────────────────────────────────────────────
@dataclass
class SwingTradeRecord:
    """개별 트레이드 결과 기록 (성과 분석용)"""
    code: str
    name: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    return_pct: float
    holding_days: int
    exit_reason: str  # "take_profit" / "stop_loss" / "time_exit"


# ──────────────────────────────────────────────
# 통합 백테스트 실행기
# ──────────────────────────────────────────────
class BacktestExecutor:
    """
    통합 백테스트 실행기
    
    strategy.strategy_type에 따라 내부 로직이 분기된다.
    - REBALANCE: 주기적 포트폴리오 리밸런싱
    - DIRECT_TRADE: 매일 스캔 + 개별 진입/청산
    """
    
    def __init__(
        self,
        strategy,
        initial_cash: float = 10_000_000,
        rebalance_interval: str = "M",  # REBALANCE용: M(월)/W(주)/Q(분기)
    ):
        self.strategy = strategy
        self.initial_cash = initial_cash
        self.rebalance_interval = rebalance_interval
    
    
    # ⚙️ 백테스트 실행 (strategy_type에 따라 분기)
    def run(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        백테스트 실행 엔트리포인트
        
        Args:
            data: {종목코드: OHLCV DataFrame (DatetimeIndex)} 딕셔너리
        
        Returns:
            pd.DataFrame (index=date):
                공통: equity, cash, holdings_value, num_holdings
                REBALANCE: rebalance (bool)
                DIRECT_TRADE: trades (list[SwingTradeRecord]) — 메타데이터
        """
        strategy_type = self.strategy.strategy_type
        
        if strategy_type == StrategyType.REBALANCE:
            return self._run_rebalance(data)
        elif strategy_type == StrategyType.DIRECT_TRADE:
            return self._run_direct_trade(data)
        else:
            raise ValueError(f"지원하지 않는 strategy_type: {strategy_type}")
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REBALANCE 로직 (기존 BacktestRunner)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ⚙️ 리밸런싱 날짜 산출 (각 주기의 첫 거래일)
    def _get_rebalance_dates(self, dates: pd.DatetimeIndex) -> set:
        groups = dates.to_period(self.rebalance_interval)
        rebalance = set()
        seen = set()
        for date, period in zip(dates, groups):
            if period not in seen:
                seen.add(period)
                rebalance.add(date)
        return rebalance
    
    
    # ⚙️ REBALANCE 백테스트 실행
    def _run_rebalance(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        포트폴리오 리밸런싱 백테스트 (기존 BacktestRunner.run 로직)
        리밸런싱 주기마다 전략 시그널을 생성하고,
        BUY 종목에 균등 분배하여 포트폴리오 equity curve를 계산
        """
        # 1. 전 종목의 공통 거래일 추출
        all_dates = sorted(
            set.intersection(*[set(df.index) for df in data.values()])
        )
        if not all_dates:
            return pd.DataFrame()
        
        # 2. 리밸런싱 날짜 추출
        dates_index = pd.DatetimeIndex(all_dates)
        rebalance_dates = self._get_rebalance_dates(dates_index)
        
        # 3. 시뮬레이션
        cash = self.initial_cash
        positions = {}  # {종목코드: 보유수량}
        records = []
        
        for date in all_dates:
            is_rebalance = date in rebalance_dates
            
            # ⭐ 리밸런싱 시점: 전략 시그널 생성 → 포트폴리오 재구성
            if is_rebalance:
                sliced = {
                    code: df.loc[:date]
                    for code, df in data.items()
                    if date in df.index
                }
                
                signals = self.strategy.generate_signal(sliced)
                buy_codes = signals[signals["signal"] == STRATEGY_SIGNAL.BUY].index.tolist()
                
                # 기존 보유 전량 청산
                for code, qty in positions.items():
                    if code in data and date in data[code].index:
                        price = data[code].loc[date, "Close"]
                        cash += qty * price
                
                positions = {}
                
                # BUY 종목에 균등 분배 매수
                if buy_codes:
                    alloc = cash / len(buy_codes)
                    for code in buy_codes:
                        price = data[code].loc[date, "Close"]
                        qty = alloc / price
                        positions[code] = qty
                    cash = 0.0
            
            # ⭐ 매일: 포트폴리오 평가
            holdings_value = 0.0
            for code, qty in positions.items():
                if date in data[code].index:
                    price = data[code].loc[date, "Close"]
                    holdings_value += qty * price
            
            total_equity = cash + holdings_value
            
            records.append({
                "date": date,
                "equity": total_equity,
                "cash": cash,
                "holdings_value": holdings_value,
                "num_holdings": len(positions),
                "rebalance": is_rebalance,
            })
        
        return pd.DataFrame(records).set_index("date")
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DIRECT_TRADE 로직 (스윙 개별매매)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ⚙️ DIRECT_TRADE 백테스트 실행
    def _run_direct_trade(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        스윙 개별매매 백테스트 (사전 로딩 데이터 기반)
        
        data에는 build_universe()에서 로딩한 유니버스 OHLCV가 들어있다.
        매일 scan_from_data()로 후보를 찾고, 개별 익절/손절/시간 청산을 관리.
        """
        s = strategy_settings
        
        # __benchmark__ 키 제외한 실제 종목 데이터
        stock_data = {k: v for k, v in data.items() if not k.startswith("__")}
        
        # 거래일 추출 (벤치마크 또는 첫 번째 종목 기준)
        if "__benchmark__" in data:
            all_dates = sorted(data["__benchmark__"].index)
        elif stock_data:
            # 모든 종목의 합집합 (교집합이 아닌 합집합 — 종목마다 거래일 다를 수 있음)
            all_date_sets = [set(df.index) for df in stock_data.values()]
            all_dates = sorted(set.union(*all_date_sets))
        else:
            return pd.DataFrame()
        
        # 유니버스 DataFrame 구성 (scan_from_data에 전달용)
        # stock_data의 키(종목코드)로 간단히 구성
        universe_records = []
        for code in stock_data.keys():
            universe_records.append({"Code": code, "Name": code})  # Name은 임시
        df_universe = pd.DataFrame(universe_records)
        
        # 시뮬레이션 상태
        cash = self.initial_cash
        positions: list[SwingPosition] = []
        trade_records: list[SwingTradeRecord] = []
        records = []
        
        for date in all_dates:
            
            # ── 1단계: 보유 종목 청산 체크 ──
            closed_indices = []
            for i, pos in enumerate(positions):
                if pos.code not in stock_data or date not in stock_data[pos.code].index:
                    continue
                
                current_price = stock_data[pos.code].loc[date, "Close"]
                return_pct = (current_price - pos.entry_price) / pos.entry_price
                pos.holding_days += 1
                
                exit_reason = None
                if return_pct >= s.RV_TAKE_PROFIT_PCT:
                    exit_reason = "take_profit"
                elif return_pct <= s.RV_STOP_LOSS_PCT:
                    exit_reason = "stop_loss"
                elif pos.holding_days >= s.RV_MAX_HOLDING_DAYS:
                    exit_reason = "time_exit"
                
                if exit_reason:
                    cash += pos.quantity * current_price
                    closed_indices.append(i)
                    
                    trade_records.append(SwingTradeRecord(
                        code=pos.code,
                        name=pos.name,
                        entry_date=pos.entry_date,
                        exit_date=date,
                        entry_price=pos.entry_price,
                        exit_price=current_price,
                        return_pct=return_pct,
                        holding_days=pos.holding_days,
                        exit_reason=exit_reason,
                    ))
            
            for i in sorted(closed_indices, reverse=True):
                positions.pop(i)
            
            # ── 2단계: 신규 진입 스캔 (사전 로딩 데이터 기반) ──
            available_slots = s.RV_MAX_POSITIONS - len(positions)
            if available_slots > 0:
                candidates = self.strategy.scan_from_data(
                    scan_date=date,
                    df_universe=df_universe,
                    preloaded_data=stock_data,
                )
                
                if not candidates.empty:
                    held_codes = {p.code for p in positions}
                    candidates = candidates[~candidates["Code"].isin(held_codes)]
                    candidates = candidates.head(available_slots)
                    
                    if len(candidates) > 0:
                        alloc_per_stock = cash / len(candidates)
                        
                        for _, row in candidates.iterrows():
                            code = row["Code"]
                            if code not in stock_data or date not in stock_data[code].index:
                                continue
                            
                            price = stock_data[code].loc[date, "Close"]
                            qty = alloc_per_stock / price
                            
                            if qty > 0 and alloc_per_stock <= cash:
                                positions.append(SwingPosition(
                                    code=code,
                                    name=row.get("Name", code),
                                    entry_price=price,
                                    quantity=qty,
                                    entry_date=date,
                                ))
                                cash -= qty * price
            
            # ── 3단계: 일일 포트폴리오 평가 ──
            holdings_value = 0.0
            for pos in positions:
                if pos.code in stock_data and date in stock_data[pos.code].index:
                    price = stock_data[pos.code].loc[date, "Close"]
                    holdings_value += pos.quantity * price
            
            total_equity = cash + holdings_value
            
            records.append({
                "date": date,
                "equity": total_equity,
                "cash": cash,
                "holdings_value": holdings_value,
                "num_holdings": len(positions),
                "rebalance": False,
            })
        
        self.trade_records = trade_records
        
        logger.info(
            f"[BacktestExecutor] DIRECT_TRADE 완료: "
            f"{len(trade_records)}건 트레이드, "
            f"최종 equity={records[-1]['equity']:,.0f}원"
        )
        
        return pd.DataFrame(records).set_index("date")