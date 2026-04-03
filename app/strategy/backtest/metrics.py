import pandas as pd
import numpy as np

from app.core.enums import STRATEGY_SIGNAL
from app.schemas.strategy.backtest import BacktestMetrics, Period, ReturnMetrics, RiskMetrics, TradeMetrics


def calculate_metrics(df: pd.DataFrame, buy_hold_return: float = 0.0, benchmark_return: float = 0.0) -> dict:
    equity = df["equity"]
    
    # 기간 (DatetimeIndex 기준)
    start_date = df.index.min()
    end_date = df.index.max()
    days = (end_date - start_date).days or 1
    
    # ⭐ ------------------ 수익률 및 알파 지표 ------------------ ⭐ #
    # 수익률
    total_return = float((equity.iloc[-1] / equity.iloc[0]) - 1)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (365 / days) - 1)
    
    # 일간 수익률
    returns = equity.pct_change().dropna()
    
    # 알파 계산
    alpha_vs_buy_hold = total_return - buy_hold_return
    alpha_vs_benchmark = total_return - benchmark_return
    
    # ⭐ ------------------ 리스크 지표 ------------------ ⭐ #
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
    
    # ⭐ ------------------ 거래 지표 ------------------ ⭐ #
    signals = df["signal"]      # 시그널 컬럼 (BUY/SELL/HOLD)
    trades = []                 # 거래별 수익률 리스트
    holding_bars_list = []      # 거래별 보유 기간 리스트
    
    entry_price = None          # 진입 가격
    entry_idx = None            # 진입 인덱스(매수 시점의 행 인덱스; 보유 기간 계산에 사용)
    
    for i in range(len(df)):
        signal = signals.iloc[i]
        price = df["Close"].iloc[i]
        
        if signal == STRATEGY_SIGNAL.BUY.value and entry_price is None:
            entry_price = price
            entry_idx = i
        
        elif signal == STRATEGY_SIGNAL.SELL.value and entry_price is not None:
            trades.append((price / entry_price) - 1)    # 거래 수익률 계산
            
            holding_bars = i - entry_idx                # 보유 기간 계산 (영업일 기준)
            holding_bars_list.append(holding_bars)      # 거래별 보유 기간 저장
            
            entry_price = None                          # 진입 가격 초기화
            entry_idx = None                            # 진입 인덱스 초기화
    
    trades = np.array(trades, dtype=float)                                                  # 거래 수익률 배열
    holding_bars_arr = np.array(holding_bars_list, dtype=float)                             # 거래 보유 기간 배열
    
    trade_count = len(trades)                                                               # 총 거래 횟수
    win_rate = float((trades > 0).mean()) if trade_count > 0 else 0.0                       # 승률
    avg_win = float(trades[trades > 0].mean()) if np.any(trades > 0) else 0.0               # 평균 수익 거래
    avg_loss = float(trades[trades < 0].mean()) if np.any(trades < 0) else 0.0              # 평균 손실 거래
    
    gross_profit = float(trades[trades > 0].sum()) if np.any(trades > 0) else 0.0           # 총 이익
    gross_loss = float(abs(trades[trades < 0].sum())) if np.any(trades < 0) else 0.0        # 총 손실
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0             # 이익 대비 손실 비율
    
    avg_holding_bars = float(holding_bars_arr.mean()) if len(holding_bars_arr) > 0 else 0.0 # 평균 보유 기간
    
    
    return BacktestMetrics(
        period=Period(
            start=str(start_date.date()),
            end=str(end_date.date()),
            days=days,
        ),
        returns=ReturnMetrics(
            total_return=round(total_return * 100, 2),
            cagr=round(cagr * 100, 2),
            buy_hold_return=round(buy_hold_return * 100, 2),
            benchmark_return=round(benchmark_return * 100, 2),
            alpha_vs_buy_hold=round(alpha_vs_buy_hold * 100, 2),
            alpha_vs_benchmark=round(alpha_vs_benchmark * 100, 2),
        ),
        risk=RiskMetrics(
            max_drawdown=round(max_drawdown * 100, 2),
            volatility=round(volatility * 100, 2),
            sharpe_ratio=round(sharpe_ratio, 2),
        ),
        trade=TradeMetrics(
            trade_count=trade_count,
            win_rate=round(win_rate * 100, 2),
            avg_win=round(avg_win * 100, 2),
            avg_loss=round(avg_loss * 100, 2),
            profit_factor=round(profit_factor, 2),
            avg_holding_bars=round(avg_holding_bars, 2),
        )
    )