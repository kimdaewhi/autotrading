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

from app.schemas.strategy.simulation import SwingPosition, SwingTradeRecord
from app.schemas.strategy.trading import StrategyType
from app.core.enums import STRATEGY_SIGNAL
from app.core.settings_strategy import strategy_settings


logger = logging.getLogger(__name__)


# ⭐ 쿨다운 판정용 최근 청산 이력 슬라이싱 윈도우
# 전략의 쿨다운 판정에 충분히 긴 기간만 넘기면 되므로
# max(cooldown_days * 2, 30)일치만 유지 → 메모리/순회 비용 절감
_TRADE_HISTORY_LOOKBACK_DAYS = 30


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
        """
        단일 종목 스윙 매매 백테스트.
        
        ⭐ 책임 분리
            - Executor(본 메서드): 시간 루프, 포지션 장부 관리, 현금 관리, 일별 평가
            - Strategy: 청산 판정, 진입 시그널 생성, 포지션 사이징
        
        ⭐ 전략 메서드 호출 지점
            - strategy.should_exit()            : 보유 포지션별 청산 판정
            - strategy.generate_entry_signals() : 진입 후보 산출 (필터 포함)
            - strategy.size_position()          : 진입 금액 결정
        """
        s = strategy_settings
        
        # __benchmark__, __universe__ 분리
        stock_data = {k: v for k, v in data.items() if not k.startswith("__")}
        df_universe = data.get("__universe__", pd.DataFrame())
        df_benchmark = data.get("__benchmark__")
        
        # 거래일 추출
        if "__benchmark__" in data:
            all_dates = sorted(data["__benchmark__"].index)
        elif stock_data:
            all_dates = sorted(set.union(*[set(df.index) for df in stock_data.values()]))
        else:
            return pd.DataFrame()
        
        # 시뮬레이션 상태
        cash = self.initial_cash
        positions: list[SwingPosition] = []
        trade_records: list[SwingTradeRecord] = []
        records = []
        
        # 쿨다운 판정용 슬라이싱 윈도우 (전략의 COOLDOWN_DAYS 보다 넉넉하게)
        history_lookback_days = max(
            getattr(s, "RV_COOLDOWN_DAYS", 0) * 2,
            _TRADE_HISTORY_LOOKBACK_DAYS,
        )
        
        for date in all_dates:
            
            # ── 1단계: 청산 체크 (전략에 판정 위임) ──
            closed = []
            for i, pos in enumerate(positions):
                # 보유일 증가는 Executor 책임 (should_exit 호출 전에 수행)
                # 데이터가 없는 날에도 증가시켜 기존 동작 유지
                pos.holding_days += 1
                
                decision = self.strategy.should_exit(pos, date, stock_data)
                
                if not decision.should_exit:
                    continue
                
                # 체결가: 당일 종가 기준 (데이터 없으면 청산 스킵 — 방어 로직)
                if pos.stock_code not in stock_data or date not in stock_data[pos.stock_code].index:
                    # 전략이 should_exit=True를 줬지만 체결할 데이터가 없음
                    # 기존 동작 유지: 청산 보류, 다음 날 재시도
                    pos.holding_days -= 1  # 증가 롤백
                    continue
                
                price = stock_data[pos.stock_code].loc[date, "Close"]
                ret = (price - pos.entry_price) / pos.entry_price       # 수익률 계산 (전략에 리턴값 넘겨줄 용도)
                
                cash += pos.quantity * price
                closed.append(i)
                trade_records.append(SwingTradeRecord(
                    stock_code=pos.stock_code,
                    stock_name=pos.stock_name,
                    entry_date=pos.entry_date,
                    exit_date=date,
                    entry_price=pos.entry_price,
                    exit_price=price,
                    quantity=pos.quantity,
                    return_pct=ret,
                    holding_days=pos.holding_days,
                    exit_reason=decision.reason.value if decision.reason else "unknown",
                ))
            
            for i in sorted(closed, reverse=True):
                positions.pop(i)
            
            # ── 2단계: 신규 진입 (전략에 시그널 + 사이징 위임) ──
            available_slots = s.RV_MAX_POSITIONS - len(positions)
            
            if available_slots > 0 and not df_universe.empty:
                # 쿨다운 판정용 최근 청산 이력만 슬라이싱해서 전략에 전달
                recent_trade_history = [
                    t for t in trade_records
                    if (date - t.exit_date).days <= history_lookback_days
                ]
                
                # 전략에 진입 시그널 요청 (필터 포함된 최종 후보가 반환됨)
                candidates = self.strategy.generate_entry_signals(
                    date=date,
                    df_universe=df_universe,
                    preloaded_data=stock_data,
                    current_positions=positions,
                    recent_trade_history=recent_trade_history,
                    df_benchmark=df_benchmark
                )
                
                # 진입 슬롯만큼만 채택
                candidates = candidates.head(available_slots)
                
                if len(candidates) > 0:
                    # 포지션 평가액 계산 (사이징 메서드에 넘길 용도)
                    current_holdings_value = sum(
                        pos.quantity * stock_data[pos.stock_code].loc[date, "Close"]
                        for pos in positions
                        if pos.stock_code in stock_data and date in stock_data[pos.stock_code].index
                    )
                    total_equity = cash + current_holdings_value
                    num_new = len(candidates)
                    
                    for _, row in candidates.iterrows():
                        code = row["Code"]
                        if code not in stock_data or date not in stock_data[code].index:
                            continue
                        
                        price = stock_data[code].loc[date, "Close"]
                        
                        # 전략에 사이징 요청
                        alloc = self.strategy.size_position(
                            signal=row,
                            available_cash=cash,
                            total_equity=total_equity,
                            num_new_entries=num_new,
                        )
                        
                        qty = alloc / price if price > 0 else 0
                        if qty > 0 and alloc <= cash:
                            positions.append(SwingPosition(
                                stock_code=code,
                                stock_name=row.get("Name", code),
                                entry_price=price,
                                quantity=qty,
                                entry_date=date,
                            ))
                            cash -= qty * price
            
            # ── 3단계: 일별 평가 ──
            holdings_value = sum(
                pos.quantity * stock_data[pos.stock_code].loc[date, "Close"]
                for pos in positions
                if pos.stock_code in stock_data and date in stock_data[pos.stock_code].index
            )
            
            records.append({
                "date": date,
                "equity": cash + holdings_value,
                "cash": cash,
                "holdings_value": holdings_value,
                "num_holdings": len(positions),
                "num_signals": len(candidates) if 'candidates' in locals() else 0,
                "rebalance": False,
            })
        
        self.trade_records = trade_records
        logger.info(
            f"[BacktestExecutor] DIRECT_TRADE 완료: "
            f"{len(trade_records)}건 트레이드, 최종 equity={records[-1]['equity']:,.0f}원"
        )
        
        return pd.DataFrame(records).set_index("date")