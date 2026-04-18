"""
통합 백테스트 실행기

⭐ 분기
    REBALANCE    → 포트폴리오 리밸런싱 (기존 BacktestRunner 로직)
    DIRECT_TRADE → 스윙 개별매매 (사전 로딩 데이터 기반)
"""
import logging
from dataclasses import dataclass

from matplotlib.style import available
import pandas as pd

from app.schemas.strategy.trading import StrategyType
from app.core.enums import STRATEGY_SIGNAL
from app.core.strategy_settings import strategy_settings


logger = logging.getLogger(__name__)


@dataclass
class SwingPosition:
    """개별 스윙 포지션"""
    stock_code: str
    stock_name: str
    entry_price: float
    quantity: float
    entry_date: pd.Timestamp
    holding_days: int = 0


@dataclass
class SwingTradeRecord:
    stock_code: str
    stock_name: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: float
    return_pct: float
    holding_days: int
    exit_reason: str


class BacktestExecutor:
    
    def __init__(self, strategy, initial_cash=10_000_000, rebalance_interval="M"):
        self.strategy = strategy
        self.initial_cash = initial_cash
        self.rebalance_interval = rebalance_interval
        self.trade_records: list[SwingTradeRecord] = []
    
    
    # ⚙️ 백테스트 실행 (strategy_type에 따라 분기)
    def run(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        strategy_type = self.strategy.strategy_type
        if strategy_type == StrategyType.REBALANCE:
            return self._run_rebalance(data)
        elif strategy_type == StrategyType.DIRECT_TRADE:
            return self._run_direct_trade(data)
        else:
            raise ValueError(f"지원하지 않는 strategy_type: {strategy_type}")
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REBALANCE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ⚙️ 리밸런싱 날짜 산출
    def _get_rebalance_dates(self, dates: pd.DatetimeIndex) -> set:
        groups = dates.to_period(self.rebalance_interval)
        rebalance, seen = set(), set()
        for date, period in zip(dates, groups):
            if period not in seen:
                seen.add(period)
                rebalance.add(date)
        return rebalance
    
    
    # ⚙️ REBALANCE 백테스트
    def _run_rebalance(self, data):
        all_dates = sorted(set.intersection(*[set(df.index) for df in data.values()]))
        if not all_dates:
            return pd.DataFrame()
        
        rebalance_dates = self._get_rebalance_dates(pd.DatetimeIndex(all_dates))
        cash = self.initial_cash
        positions = {}
        records = []
        
        for date in all_dates:
            is_rebalance = date in rebalance_dates
            
            if is_rebalance:
                sliced = {c: df.loc[:date] for c, df in data.items() if date in df.index}
                signals = self.strategy.generate_signal(sliced)
                buy_codes = signals[signals["signal"] == STRATEGY_SIGNAL.BUY].index.tolist()
                
                for code, qty in positions.items():
                    if code in data and date in data[code].index:
                        cash += qty * data[code].loc[date, "Close"]
                positions = {}
                
                if buy_codes:
                    alloc = cash / len(buy_codes)
                    for code in buy_codes:
                        positions[code] = alloc / data[code].loc[date, "Close"]
                    cash = 0.0
            
            holdings_value = sum(
                qty * data[c].loc[date, "Close"]
                for c, qty in positions.items()
                if date in data[c].index
            )
            
            records.append({
                "date": date, "equity": cash + holdings_value, "cash": cash,
                "holdings_value": holdings_value, "num_holdings": len(positions),
                "rebalance": is_rebalance,
            })
        
        return pd.DataFrame(records).set_index("date")
    
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DIRECT_TRADE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ⚙️ DIRECT_TRADE 백테스트
    def _run_direct_trade(self, data):
        s = strategy_settings
        
        # __benchmark__, __universe__ 분리
        stock_data = {k: v for k, v in data.items() if not k.startswith("__")}
        df_universe = data.get("__universe__", pd.DataFrame())
        
        # 거래일 추출
        if "__benchmark__" in data:
            all_dates = sorted(data["__benchmark__"].index)
        elif stock_data:
            all_dates = sorted(set.union(*[set(df.index) for df in stock_data.values()]))
        else:
            return pd.DataFrame()
        
        # 시뮬레이션
        cash = self.initial_cash
        positions: list[SwingPosition] = []
        trade_records: list[SwingTradeRecord] = []
        records = []
        
        for date in all_dates:
            
            # ── 1단계: 청산 체크 ──
            closed = []
            for i, pos in enumerate(positions):
                if pos.stock_code not in stock_data or date not in stock_data[pos.stock_code].index:
                    continue
                
                price = stock_data[pos.stock_code].loc[date, "Close"]
                ret = (price - pos.entry_price) / pos.entry_price
                pos.holding_days += 1
                
                exit_reason = None
                if ret >= s.RV_TAKE_PROFIT_PCT:
                    exit_reason = "take_profit"
                elif ret <= s.RV_STOP_LOSS_PCT:
                    exit_reason = "stop_loss"
                elif pos.holding_days >= s.RV_MAX_HOLDING_DAYS:
                    exit_reason = "time_exit"
                
                if exit_reason:
                    cash += pos.quantity * price
                    closed.append(i)
                    trade_records.append(SwingTradeRecord(
                        stock_code=pos.stock_code, stock_name=pos.stock_name,
                        entry_date=pos.entry_date, exit_date=date,
                        entry_price=pos.entry_price, exit_price=price,
                        quantity=pos.quantity,
                        return_pct=ret, holding_days=pos.holding_days,
                        exit_reason=exit_reason,
                    ))
            
            for i in sorted(closed, reverse=True):
                positions.pop(i)
            
            # ── 2단계: 신규 진입 ──
            # 하락장 필터: KOSPI가 20일 이평 아래면 진입 금지
            # if s.RV_MARKET_FILTER_ENABLED and "__benchmark__" in data:
            #     bench = data["__benchmark__"]
            #     if date in bench.index:
            #         ma = bench["Close"].loc[:date].tail(s.RV_MARKET_MA_DAYS).mean()
            #         if bench.loc[date, "Close"] < ma:
            #             continue  # 이 날은 진입 스킵
                    
            available = s.RV_MAX_POSITIONS - len(positions)
            if available > 0 and not df_universe.empty:
                candidates = self.strategy.scan_from_data(date, df_universe, stock_data)
                
                if not candidates.empty:
                    candidates_before = len(candidates)
                    
                    held = {p.stock_code for p in positions}
                    recent_exits = {
                        t.stock_code for t in trade_records
                        if (date - t.exit_date).days <= s.RV_COOLDOWN_DAYS
                    }
                    
                    # ── 쿨다운 진단 로그 ──
                    blocked_by_held = set(candidates["Code"]) & held
                    blocked_by_cooldown = set(candidates["Code"]) & recent_exits - held
                    
                    if blocked_by_cooldown:
                        logger.info(
                            f"[COOLDOWN] date={date.date()}, "
                            f"candidates={candidates_before}, "
                            f"blocked_by_held={len(blocked_by_held)}, "
                            f"blocked_by_cooldown={len(blocked_by_cooldown)}, "
                            f"cooldown_codes={blocked_by_cooldown}, "
                            f"recent_exits_size={len(recent_exits)}"
                        )
                    
                    candidates = candidates[~candidates["Code"].isin(held | recent_exits)]
                    candidates = candidates.head(available)
                    
                    if len(candidates) > 0:
                        alloc = cash / len(candidates)
                        
                        for _, row in candidates.iterrows():
                            code = row["Code"]
                            if code not in stock_data or date not in stock_data[code].index:
                                continue
                            price = stock_data[code].loc[date, "Close"]
                            qty = alloc / price
                            if qty > 0 and alloc <= cash:
                                positions.append(SwingPosition(
                                    stock_code=code,
                                    stock_name=row.get("Name", code),
                                    entry_price=price, quantity=qty, entry_date=date,
                                ))
                                cash -= qty * price
            
            # ── 3단계: 평가 ──
            holdings_value = sum(
                pos.quantity * stock_data[pos.stock_code].loc[date, "Close"]
                for pos in positions
                if pos.stock_code in stock_data and date in stock_data[pos.stock_code].index
            )
            
            records.append({
                "date": date, "equity": cash + holdings_value, "cash": cash,
                "holdings_value": holdings_value, "num_holdings": len(positions),
                "rebalance": False,
            })
        
        self.trade_records = trade_records
        logger.info(
            f"[BacktestExecutor] DIRECT_TRADE 완료: "
            f"{len(trade_records)}건 트레이드, 최종 equity={records[-1]['equity']:,.0f}원"
        )
        
        return pd.DataFrame(records).set_index("date")