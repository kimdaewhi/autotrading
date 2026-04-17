import pandas as pd
import numpy as np

from app.schemas.strategy.backtest import (
    BacktestMetrics,
    Period,
    ReturnMetrics,
    RiskMetrics,
    RebalanceTradeMetrics,
    SwingTradeMetrics,
)


def calculate_metrics(
    df: pd.DataFrame,
    benchmark_return: float = 0.0,
    trade_records: list | None = None,
) -> BacktestMetrics:
    """
    백테스트 결과 DataFrame에서 성과 지표를 계산
    
    Parameters
    ----------
    df : pd.DataFrame
        BacktestExecutor.run() 반환값 (equity, cash, holdings_value, num_holdings, rebalance)
    benchmark_return : float
        벤치마크 수익률
    trade_records : list[SwingTradeRecord] | None
        DIRECT_TRADE일 때 개별 트레이드 기록.
        None이면 REBALANCE 모드로 리밸런싱 구간 기반 계산.
    """
    equity = df["equity"]

    # 기간
    start_date = df.index.min()
    end_date = df.index.max()
    days = (end_date - start_date).days or 1

    # ⭐ ------------------ 수익률 지표 ------------------ ⭐ #
    total_return = float((equity.iloc[-1] / equity.iloc[0]) - 1)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (365 / days) - 1)
    alpha_vs_benchmark = total_return - benchmark_return

    # 일간 수익률
    returns = equity.pct_change().dropna()

    # ⭐ ------------------ 리스크 지표 ------------------ ⭐ #
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_drawdown = float(drawdown.min())

    volatility = float(returns.std() * np.sqrt(252)) if not returns.empty else 0.0

    sharpe_ratio = (
        float((returns.mean() / returns.std()) * np.sqrt(252))
        if not returns.empty and returns.std() != 0
        else 0.0
    )

    # ⭐ ------------------ 거래 지표 (전략 타입별 분기) ------------------ ⭐ #
    if trade_records is not None:
        trade_metrics = _calc_swing_trade_metrics(df, trade_records)
    else:
        trade_metrics = _calc_rebalance_trade_metrics(df, equity)

    return BacktestMetrics(
        period=Period(
            start=str(start_date.date()),
            end=str(end_date.date()),
            days=days,
        ),
        returns=ReturnMetrics(
            total_return=round(total_return * 100, 2),
            cagr=round(cagr * 100, 2),
            benchmark_return=round(benchmark_return * 100, 2),
            alpha_vs_benchmark=round(alpha_vs_benchmark * 100, 2),
        ),
        risk=RiskMetrics(
            max_drawdown=round(max_drawdown * 100, 2),
            volatility=round(volatility * 100, 2),
            sharpe_ratio=round(sharpe_ratio, 2),
        ),
        trade=trade_metrics,
    )


# ⚙️ REBALANCE용 거래 지표 (리밸런싱 구간 기준)
def _calc_rebalance_trade_metrics(df: pd.DataFrame, equity: pd.Series) -> RebalanceTradeMetrics:
    rebalance_mask = df["rebalance"] == True
    rebalance_indices = df.index[rebalance_mask].tolist()
    rebalance_count = len(rebalance_indices)

    # 리밸런싱 구간별 수익률 계산
    period_returns = []
    for i in range(len(rebalance_indices)):
        start_eq = equity.loc[rebalance_indices[i]]
        if i + 1 < len(rebalance_indices):
            end_eq = equity.loc[rebalance_indices[i + 1]]
        else:
            end_eq = equity.iloc[-1]
        period_ret = (end_eq / start_eq) - 1
        period_returns.append(period_ret)

    period_returns = np.array(period_returns, dtype=float)
    
    win_rate = float((period_returns > 0).mean()) if len(period_returns) > 0 else 0.0
    avg_win = float(period_returns[period_returns > 0].mean()) if np.any(period_returns > 0) else 0.0
    avg_loss = float(period_returns[period_returns < 0].mean()) if np.any(period_returns < 0) else 0.0
    
    gross_profit = float(period_returns[period_returns > 0].sum()) if np.any(period_returns > 0) else 0.0
    gross_loss = float(abs(period_returns[period_returns < 0].sum())) if np.any(period_returns < 0) else 0.0
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0
    
    avg_holding_count = float(df["num_holdings"].mean())
    
    return RebalanceTradeMetrics(
        rebalance_count=rebalance_count,
        win_rate=round(win_rate * 100, 2),
        avg_win=round(avg_win * 100, 2),
        avg_loss=round(avg_loss * 100, 2),
        profit_factor=round(profit_factor, 2),
        avg_holding_count=round(avg_holding_count, 2),
    )


# ⚙️ DIRECT_TRADE용 거래 지표 (개별 트레이드 기준)
def _calc_swing_trade_metrics(df: pd.DataFrame, trade_records: list) -> SwingTradeMetrics:
    trade_count = len(trade_records)
    
    if trade_count == 0:
        return SwingTradeMetrics(
            trade_count=0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            avg_holding_days=0.0,
            avg_holding_count=float(df["num_holdings"].mean()),
            take_profit_pct=0.0,
            stop_loss_pct=0.0,
            time_exit_pct=0.0,
        )
    
    # 트레이드별 수익률 배열
    trade_returns = np.array([t.return_pct for t in trade_records], dtype=float)
    holding_days = np.array([t.holding_days for t in trade_records], dtype=float)
    
    # 승률
    win_rate = float((trade_returns > 0).mean())
    avg_win = float(trade_returns[trade_returns > 0].mean()) if np.any(trade_returns > 0) else 0.0
    avg_loss = float(trade_returns[trade_returns < 0].mean()) if np.any(trade_returns < 0) else 0.0
    
    # Profit Factor
    gross_profit = float(trade_returns[trade_returns > 0].sum()) if np.any(trade_returns > 0) else 0.0
    gross_loss = float(abs(trade_returns[trade_returns < 0].sum())) if np.any(trade_returns < 0) else 0.0
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0
    
    # 평균 보유일
    avg_holding_days = float(holding_days.mean())
    
    # 평균 보유 종목 수
    avg_holding_count = float(df["num_holdings"].mean())
    
    # 청산 사유별 비율
    exit_reasons = [t.exit_reason for t in trade_records]
    take_profit_count = exit_reasons.count("take_profit")
    stop_loss_count = exit_reasons.count("stop_loss")
    time_exit_count = exit_reasons.count("time_exit")
    
    take_profit_pct = (take_profit_count / trade_count) * 100
    stop_loss_pct = (stop_loss_count / trade_count) * 100
    time_exit_pct = (time_exit_count / trade_count) * 100
    
    return SwingTradeMetrics(
        trade_count=trade_count,
        win_rate=round(win_rate * 100, 2),
        avg_win=round(avg_win * 100, 2),
        avg_loss=round(avg_loss * 100, 2),
        profit_factor=round(profit_factor, 2),
        avg_holding_days=round(avg_holding_days, 2),
        avg_holding_count=round(avg_holding_count, 2),
        take_profit_pct=round(take_profit_pct, 2),
        stop_loss_pct=round(stop_loss_pct, 2),
        time_exit_pct=round(time_exit_pct, 2),
    )