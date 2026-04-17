from matplotlib import ticker
import matplotlib.pyplot as plt
import numpy as np
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






# ⚙️ 종목별 equity 기여도 시각화
def plot_equity_contribution(
    df_result: pd.DataFrame,
    trade_records: list,
    preloaded_data: dict[str, pd.DataFrame] = None,
    benchmark_df: pd.DataFrame = None,
    top_n: int = 10,
):
    """
    종목별 equity 기여도 시각화
    
    - 상단: 전체 equity curve + 종목별 기여도 area chart
    - 하단: 종목별 누적 손익 bar chart
    
    trade_records에서 역산:
        각 트레이드의 진입~청산 구간에서 일일 평가액 변동을 추적
    """
    if not trade_records:
        print("트레이드 기록이 없습니다.")
        return
    
    initial_equity = df_result["equity"].iloc[0]
    all_dates = df_result.index
    
    # ── 종목별 일일 손익 계산 ──
    # 각 트레이드에서 진입 금액 대비 일일 평가손익을 계산
    stock_daily_pnl = {}  # {stock_name: Series(date → pnl)}
    
    for t in trade_records:
        name = t.stock_name
        if name not in stock_daily_pnl:
            stock_daily_pnl[name] = pd.Series(0.0, index=all_dates)
        
        # 진입 금액 (전체 자금 / 동시보유수 근사 → 단순히 수익률 × 가중치로)
        # trade_records에 quantity * price 정보가 있으니 활용
        entry_value = t.entry_price * t.quantity
        
        # 진입일~청산일 구간의 날짜
        mask = (all_dates >= t.entry_date) & (all_dates <= t.exit_date)
        trade_dates = all_dates[mask]
        
        if len(trade_dates) == 0:
            continue
        
        # 해당 구간의 일일 수익률 계산 (preloaded_data 있으면 정확히, 없으면 선형 보간)
        if preloaded_data and t.stock_code in preloaded_data:
            ohlcv = preloaded_data[t.stock_code]
            for date in trade_dates:
                if date in ohlcv.index:
                    current_price = ohlcv.loc[date, "Close"]
                    daily_pnl = (current_price - t.entry_price) / t.entry_price * entry_value
                    stock_daily_pnl[name].loc[date] += daily_pnl
        else:
            # preloaded_data 없으면 선형 보간
            total_pnl = t.return_pct * entry_value
            for i, date in enumerate(trade_dates):
                ratio = (i + 1) / len(trade_dates)
                stock_daily_pnl[name].loc[date] += total_pnl * ratio
    
    # DataFrame으로 변환
    df_contrib = pd.DataFrame(stock_daily_pnl)
    
    # 종목별 최종 누적 손익 기준 상위 N개
    final_pnl = df_contrib.iloc[-1].sort_values(ascending=False)
    top_stocks = final_pnl.head(top_n).index.tolist()
    bottom_stocks = final_pnl.tail(min(5, len(final_pnl))).index.tolist()
    
    # 나머지는 "기타"로 합산
    show_stocks = list(dict.fromkeys(top_stocks + bottom_stocks))  # 중복 제거
    df_show = df_contrib[show_stocks].copy()
    others = df_contrib.drop(columns=show_stocks, errors="ignore")
    if not others.empty:
        df_show["기타"] = others.sum(axis=1)
    
    # ── 시각화 ──
    fig, axes = plt.subplots(2, 1, figsize=(14, 10),
                             gridspec_kw={"height_ratios": [3, 1.5]})
    
    # 상단: Equity curve + 종목별 기여 영역
    ax1 = axes[0]
    
    # 전체 equity
    ax1.plot(df_result.index, df_result["equity"], color="black", linewidth=1.5, label="Portfolio", zorder=10)
    
    # 벤치마크
    if benchmark_df is not None:
        bench_norm = (benchmark_df["Close"] / benchmark_df["Close"].iloc[0]) * initial_equity
        common_idx = df_result.index.intersection(bench_norm.index)
        ax1.plot(common_idx, bench_norm.loc[common_idx],
                 color="gray", linewidth=0.9, linestyle="--", alpha=0.7, label="Benchmark")
    
    # 종목별 기여도를 equity 위에 표시
    # 초기 자본 + 종목별 누적 손익
    colors = plt.cm.tab20(np.linspace(0, 1, len(df_show.columns)))
    
    for i, col in enumerate(df_show.columns):
        alpha = 0.6 if col != "기타" else 0.3
        ax1.fill_between(
            df_show.index,
            initial_equity + df_show[col],
            initial_equity,
            alpha=alpha, color=colors[i], label=col, linewidth=0,
        )
    
    ax1.set_title("Equity Curve + 종목별 기여도", fontsize=13)
    ax1.set_ylabel("₩")
    ax1.legend(loc="upper left", fontsize=8, ncol=2)
    ax1.grid(alpha=0.3)
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{x/1e6:.1f}M'))
    
    # 하단: 종목별 최종 누적 손익 bar
    ax2 = axes[1]
    
    all_final = final_pnl.head(15)  # 상위 15개
    bar_colors = ["green" if v >= 0 else "red" for v in all_final.values]
    bars = ax2.barh(range(len(all_final)), all_final.values, color=bar_colors, alpha=0.7)
    ax2.set_yticks(range(len(all_final)))
    ax2.set_yticklabels(all_final.index, fontsize=9)
    ax2.invert_yaxis()
    ax2.set_xlabel("누적 손익 (₩)")
    ax2.set_title("종목별 누적 손익 (상위 15)", fontsize=13)
    ax2.grid(alpha=0.3, axis="x")
    ax2.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{x/1e4:.0f}만'))
    
    # 값 라벨
    for bar, val in zip(bars, all_final.values):
        ax2.text(val, bar.get_y() + bar.get_height()/2,
                f' {val/10000:+,.0f}만원', va="center", fontsize=8)
    
    plt.tight_layout()
    plt.show()