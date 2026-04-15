import pandas as pd

from app.core.enums import STRATEGY_SIGNAL


class MACrossStrategy():

    def __init__(self, short_window: int = 5, long_window: int = 20):
        self.short_window = short_window
        self.long_window = long_window
    
    
    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        df = data.copy()
        
        df["ma_short"] = df["Close"].rolling(self.short_window).mean()
        df["ma_long"] = df["Close"].rolling(self.long_window).mean()
        
        signal = pd.Series(STRATEGY_SIGNAL.HOLD, index=df.index)
        
        # 골든크로스
        buy_condition = (
            (df["ma_short"].shift(1) <= df["ma_long"].shift(1)) &
            (df["ma_short"] > df["ma_long"])
        )
        
        # 데드크로스
        sell_condition = (
            (df["ma_short"].shift(1) >= df["ma_long"].shift(1)) &
            (df["ma_short"] < df["ma_long"])
        )
        
        signal[buy_condition] = STRATEGY_SIGNAL.BUY
        signal[sell_condition] = STRATEGY_SIGNAL.SELL
        
        return signal