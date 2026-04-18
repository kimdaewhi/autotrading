import pandas as pd
from dataclasses import dataclass

"""
"""

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