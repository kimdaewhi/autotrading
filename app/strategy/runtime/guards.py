import pandas as pd


def validate_ohlcv(data: pd.DataFrame):
    required_columns = ["Open", "High", "Low", "Close", "Volume"]
    
    for col in required_columns:
        if col not in data.columns:
            raise ValueError(f"Missing column: {col}")
    
    if data.empty:
        raise ValueError("Empty OHLCV data")