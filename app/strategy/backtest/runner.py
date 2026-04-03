import pandas as pd

from app.strategy.strategies.base_strategy import BaseStrategy
from app.core.enums import STRATEGY_SIGNAL


class BacktestRunner:
    """
    백테스트 전용 실행기.
    전략 시그널을 기반으로
    자산 흐름(equity curve)을 계산하는 실행기
    """

    def __init__(self, strategy: BaseStrategy, initial_cash: float = 1_000_000):
        self.strategy = strategy
        self.initial_cash = initial_cash
    
    # ⚙️ 백테스트 실행 (단일 전략 기준)
    def run(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        # 전략 → 시그널 생성
        signals = self.strategy.generate_signal(df)
        
        cash = self.initial_cash   # 보유 현금
        position = 0               # 보유 수량 (주식)
        equity_curve = []          # 시간별 총 자산
        
        for i in range(len(df)):
            price = df["Close"].iloc[i]
            signal = signals.iloc[i]
            
            # 매수: 전액 진입
            if signal == STRATEGY_SIGNAL.BUY and cash > 0:
                position = cash / price
                cash = 0
            
            # 매도: 전량 청산
            elif signal == STRATEGY_SIGNAL.SELL and position > 0:
                cash = position * price
                position = 0
            
            # 현재 총 자산 = 현금 + 평가금액
            total_value = cash + position * price
            equity_curve.append(total_value)
        
        df["equity"] = equity_curve   # 자산 흐름
        df["signal"] = signals        # 시그널 기록
        
        return df