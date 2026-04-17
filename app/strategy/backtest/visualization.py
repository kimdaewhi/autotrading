import matplotlib.pyplot as plt
import pandas as pd


def plot_backtest_result(
    df: pd.DataFrame,
    benchmark_df: pd.DataFrame = None,
    trade_records: list = None,
):
    """
    백테스트 결과 시각화 (REBALANCE / DIRECT_TRADE 자동 분기)
    
    - 상단: equity curve + 벤치마크 + 트레이드 마커 (또는 리밸런싱 시점)
    - 중단: drawdown curve
    - 하단: 보유 종목 수 변화
    """
    fig, axes = plt.subplots(
        3, 
        1, 
        figsize=(14, 10),
        gridspec_kw={"height_ratios": [3, 1, 1]}, 
        sharex=True
    )

    # ⭐ 상단: Equity Curve + Benchmark
    ax1 = axes[0]
    ax1.plot(df.index, df["equity"], label="Portfolio", color="black", linewidth=1.2)

    if benchmark_df is not None:
        initial_equity = df["equity"].iloc[0]
        bench_norm = (benchmark_df["Close"] / benchmark_df["Close"].iloc[0]) * initial_equity
        common_idx = df.index.intersection(bench_norm.index)
        ax1.plot(
            common_idx, 
            bench_norm.loc[common_idx],
            label="Benchmark (KOSPI)", color="gray", linewidth=0.9,
            linestyle="--", alpha=0.7
        )

    if trade_records:
        # DIRECT_TRADE: 진입/청산 마커
        for t in trade_records:
            color = "green" if t.return_pct > 0 else "red"
            # 진입
            if t.entry_date in df.index:
                ax1.scatter(
                    t.entry_date, 
                    df.loc[t.entry_date, "equity"],
                    marker="^", 
                    color=color, 
                    s=25, 
                    zorder=5, 
                    alpha=0.7
                )
            # 청산
            if t.exit_date in df.index:
                ax1.scatter(
                    t.exit_date, 
                    df.loc[t.exit_date, "equity"],
                    marker="v", 
                    color=color, 
                    s=25, 
                    zorder=5, 
                    alpha=0.7
                )
    else:
        # REBALANCE: 리밸런싱 시점
        rebalance = df[df["rebalance"] == True]
        ax1.scatter(
            rebalance.index, 
            rebalance["equity"],
            marker="D", 
            color="royalblue", 
            s=30, 
            label="Rebalance", 
            zorder=5
        )

    ax1.set_title("Portfolio Backtest Result")
    ax1.set_ylabel("Equity (₩)")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)

    # ⭐ 중단: Drawdown
    ax2 = axes[1]
    cummax = df["equity"].cummax()
    drawdown = (df["equity"] - cummax) / cummax * 100
    ax2.fill_between(df.index, drawdown, 0, color="salmon", alpha=0.5)
    ax2.set_ylabel("Drawdown (%)")
    ax2.grid(alpha=0.3)

    # ⭐ 하단: 보유 종목 수
    ax3 = axes[2]
    ax3.fill_between(
        df.index, df["num_holdings"], 
        0,
        color="steelblue", 
        alpha=0.4, 
        step="post"
    )
    ax3.set_ylabel("Holdings")
    ax3.set_xlabel("Date")
    ax3.set_ylim(0, max(df["num_holdings"].max(), 1) + 1)
    ax3.grid(alpha=0.3)

    plt.tight_layout()
    plt.show()