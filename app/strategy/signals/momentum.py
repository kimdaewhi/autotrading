import pandas as pd

from app.strategy.signals.base_strategy import BaseStrategy
from app.core.enums import STRATEGY_SIGNAL


class MomentumStrategy(BaseStrategy):
    """_summary_
    ⭐ Lookback 이란? 과거 일정 기간 동안의 가격 변동을 분석하는 방법
    
    """
    def __init__(self, lookback_days: int = 120, top_n: int = 10, abs_threshold: float = 0.0):
        """
        Parameters
        ----------
        lookback_days : int
            과거 일정 기간 동안의 가격 변동을 분석하는 기간
        top_n : int
            상대 모멘텀 상위 N개 종목 선정
        abs_threshold : float
            절대 모멘텀 기준 수익률
        """
        self.lookback_days = lookback_days
        self.top_n = top_n
        self.abs_threshold = abs_threshold
    
    def generate_signal(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        듀얼 모멘텀 전략
        1) 각 종목의 룩백 기간 수익률 계산
        2) 상대 모멘텀: 수익률 상위 top_n 종목 선정
        3) 절대 모멘텀: 수익률이 abs_threshold 이하인 종목 제외
        """
        returns = {}
        
        # 1. 각 종목의 룩백 기간 수익률 계산 
        for code, df in data.items():
            # 충분한 데이터가 없는 경우 건너뛰기
            if len(df) < self.lookback_days:
                continue
            
            # 최근 lookback_days 기간의 수익률 계산
            recent = df["Close"].iloc[-self.lookback_days:]
            ret = (recent.iloc[-1] - recent.iloc[0]) / recent.iloc[0]
            returns[code] = ret
        
        # 2. 상대 모멘텀: 수익률 상위 top_n 종목 선정
        if not returns:
            return pd.DataFrame(columns=["signal", "return", "rank"])
        
        # 3. 절대 모멘텀: 수익률이 abs_threshold 이하인 종목 제외
        result = pd.DataFrame({
            "return": pd.Series(returns),
        })
        
        # 상대 모멘텀: 수익률 기준 순위
        result["rank"] = result["return"].rank(ascending=False)
        
        # 듀얼 모멘텀: 상위 N개 + 절대 모멘텀 통과
        result["signal"] = STRATEGY_SIGNAL.HOLD
        
        # BUY: 순위 내 + 수익률 > 절대 모멘텀 기준
        buy_mask = (
            (result["rank"] <= self.top_n) &
            (result["return"] > self.abs_threshold)
        )
        result.loc[buy_mask, "signal"] = STRATEGY_SIGNAL.BUY

        # 기존 보유 중인데 순위 밖이면 SELL
        sell_mask = ~buy_mask
        result.loc[sell_mask, "signal"] = STRATEGY_SIGNAL.SELL

        return result.sort_values("rank")