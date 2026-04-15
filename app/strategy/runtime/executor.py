from typing import List
import pandas as pd

from app.strategy.signals.base_strategy import BaseStrategy


class StrategyExecutor:

    def __init__(self, strategies: List[BaseStrategy]):
        self.strategies = strategies

    def run(self, data: pd.DataFrame) -> dict:
        """
        여러 전략 실행
        return: {strategy_name: signals}
        """
        results = {}

        for strategy in self.strategies:
            name = strategy.__class__.__name__
            signals = strategy.generate_signal(data)
            results[name] = signals

        return results