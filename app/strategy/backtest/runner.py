import pandas as pd
import numpy as np

from app.strategy.signals.base_signal import BaseSignal
from app.core.enums import STRATEGY_SIGNAL


class BacktestRunner:
    """
    백테스트 전용 실행기 (포트폴리오 기준)
    리밸런싱 주기마다 전략 시그널을 생성하고,
    BUY 종목에 균등 분배하여 포트폴리오 equity curve를 계산
    """
    
    def __init__(
        self,
        strategy: BaseSignal,
        initial_cash: float = 10_000_000,
        rebalance_interval: str = "M",  # M: 월말, W: 주말, Q: 분기말
    ):
        self.strategy = strategy
        self.initial_cash = initial_cash
        self.rebalance_interval = rebalance_interval
    
    
    # ⚙️ 리밸런싱 날짜 산출 (각 주기의 첫 거래일)
    def _get_rebalance_dates(self, dates: pd.DatetimeIndex) -> set:
        """
        리밸런싱 날짜 산출 (각 주기의 첫 거래일)
        """
        groups = dates.to_period(self.rebalance_interval)
        rebalance = set()
        
        seen = set()
        for date, period in zip(dates, groups):
            if period not in seen:
                seen.add(period)
                rebalance.add(date)
        
        return rebalance
    
    
    # ⚙️ 핵심 로직: 백테스트 실행
    def run(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        포트폴리오 백테스트 실행

        Args:
            data: {종목코드: OHLCV DataFrame (DatetimeIndex)} 딕셔너리

        Returns:
            pd.DataFrame:
                - index: 날짜
                - columns: equity, cash, holdings_value, num_holdings, rebalance
        """
        # 1. 전 종목의 공통 거래일 추출
        all_dates = sorted(
            set.intersection(*[set(df.index) for df in data.values()])
        )
        
        if not all_dates:
            return pd.DataFrame()
        
        # 2. 리밸런싱 날짜 추출 (각 월의 첫 거래일)
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
                # 현재 시점까지의 데이터만 잘라서 전략에 전달
                sliced = {
                    code: df.loc[:date]
                    for code, df in data.items()
                    if date in df.index
                }
                
                signals = self.strategy.generate_signal(sliced)
                buy_codes = signals[signals["signal"] == STRATEGY_SIGNAL.BUY].index.tolist()
                
                # 기존 보유 전량 청산 (리밸런싱이니까)
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
        
        result = pd.DataFrame(records).set_index("date")
        return result