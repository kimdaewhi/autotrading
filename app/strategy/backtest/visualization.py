import matplotlib.pyplot as plt

def plot_backtest_result(df):
    plt.figure(figsize=(12, 6))

    # 가격 라인
    plt.plot(df.index, df["Close"], label="Price", color="black")

    # 매수 포인트
    buy = df[df["signal"] == "BUY"]
    plt.scatter(buy.index, buy["Close"], marker="^", color="green", label="BUY")

    # 매도 포인트
    sell = df[df["signal"] == "SELL"]
    plt.scatter(sell.index, sell["Close"], marker="v", color="red", label="SELL")

    plt.title("Backtest Result")
    plt.legend()
    plt.grid()

    plt.show()