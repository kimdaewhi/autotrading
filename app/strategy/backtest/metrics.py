import pandas as pd
import numpy as np


def calculate_metrics(df: pd.DataFrame) -> dict:
    equity = df["equity"]

    # 기간 (DatetimeIndex 기준)
    start_date = df.index.min()
    end_date = df.index.max()
    days = (end_date - start_date).days or 1

    # 수익률
    total_return = float((equity.iloc[-1] / equity.iloc[0]) - 1)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (365 / days) - 1)

    # 일간 수익률
    returns = equity.pct_change().dropna()

    # MDD
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_drawdown = float(drawdown.min())

    # 변동성 (연환산)
    volatility = float(returns.std() * np.sqrt(252)) if not returns.empty else 0.0

    # 샤프비율 (무위험수익률 0 가정)
    sharpe_ratio = (
        float((returns.mean() / returns.std()) * np.sqrt(252))
        if not returns.empty and returns.std() != 0
        else 0.0
    )

    # 거래 분석
    signals = df["signal"]
    trades = []
    entry_price = None

    for i in range(len(df)):
        signal = signals.iloc[i]
        price = df["Close"].iloc[i]

        if signal == "BUY" and entry_price is None:
            entry_price = price

        elif signal == "SELL" and entry_price is not None:
            trades.append((price / entry_price) - 1)
            entry_price = None

    trades = np.array(trades, dtype=float)

    trade_count = len(trades)
    win_rate = float((trades > 0).mean()) if trade_count > 0 else 0.0
    avg_win = float(trades[trades > 0].mean()) if np.any(trades > 0) else 0.0
    avg_loss = float(trades[trades < 0].mean()) if np.any(trades < 0) else 0.0

    gross_profit = float(trades[trades > 0].sum()) if np.any(trades > 0) else 0.0
    gross_loss = float(abs(trades[trades < 0].sum())) if np.any(trades < 0) else 0.0
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0

    return {
        "period": {
            "start": str(start_date.date()),   # 백테스트 시작일
            "end": str(end_date.date()),       # 백테스트 종료일
            "days": days,                      # 총 기간 (일수)
        },
        "return": {
            "total_return(%)": round(total_return * 100, 2),  # 전체 기간 수익률
            "cagr(%)": round(cagr * 100, 2),                  # 연환산 수익률
        },
        "risk": {
            "max_drawdown(%)": round(max_drawdown * 100, 2),  # 최대 낙폭 (최고점 대비 손실)
            "volatility(%)": round(volatility * 100, 2),      # 변동성 (연환산 표준편차)
            "sharpe_ratio": round(sharpe_ratio, 2),           # 수익 대비 변동성 (위험 대비 성과)
        },
        "trade": {
            "trade_count": trade_count,                       # 총 거래 횟수 (BUY→SELL 완료 기준)
            "win_rate(%)": round(win_rate * 100, 2),          # 승률 (이익 거래 비율)
            "avg_win(%)": round(avg_win * 100, 2),            # 평균 이익 거래 수익률
            "avg_loss(%)": round(avg_loss * 100, 2),          # 평균 손실 거래 수익률
            "profit_factor": round(profit_factor, 2),         # 총 이익 / 총 손실 (1 이상이면 유리)
        },
    }