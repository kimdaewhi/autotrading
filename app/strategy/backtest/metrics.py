import pandas as pd


def calculate_metrics(df: pd.DataFrame) -> dict:
    equity = df["equity"]

    total_return = float((equity.iloc[-1] / equity.iloc[0]) - 1)

    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_drawdown = float(drawdown.min())

    return {
        "total_return": round(total_return * 100, 2),   # %
        "max_drawdown": round(max_drawdown * 100, 2),   # %
    }