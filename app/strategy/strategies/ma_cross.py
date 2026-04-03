import pandas as pd

from app.strategy.strategies.base_strategy import BaseStrategy
from app.core.enums import STRATEGY_SIGNAL


class MACrossStrategy(BaseStrategy):

    def __init__(self, short_window: int = 5, long_window: int = 20):
        self.short_window = short_window
        self.long_window = long_window
    
    
    # ⚙️ 이동평균 교차 전략 구현
    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        df = data.copy()
        
        # 이동평균 계산
        df["ma_short"] = df["Close"].rolling(self.short_window).mean()
        df["ma_long"] = df["Close"].rolling(self.long_window).mean()
        
        signal = []
        
        for i in range(len(df)):
            if i == 0:
                signal.append(STRATEGY_SIGNAL.HOLD)
                continue
            
            prev_short = df["ma_short"].iloc[i - 1]
            prev_long = df["ma_long"].iloc[i - 1]
            curr_short = df["ma_short"].iloc[i]
            curr_long = df["ma_long"].iloc[i]
            
            # NaN 구간 방어
            if pd.isna(prev_short) or pd.isna(prev_long) or pd.isna(curr_short) or pd.isna(curr_long):
                signal.append(STRATEGY_SIGNAL.HOLD)
                continue
                
            # 골든크로스
            if prev_short <= prev_long and curr_short > curr_long:
                signal.append(STRATEGY_SIGNAL.BUY)
            
            # 데드크로스
            elif prev_short >= prev_long and curr_short < curr_long:
                signal.append(STRATEGY_SIGNAL.SELL)
            
            else:
                signal.append(STRATEGY_SIGNAL.HOLD)
        
        return pd.Series(signal, index=df.index)