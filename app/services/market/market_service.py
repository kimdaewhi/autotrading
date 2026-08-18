import datetime
import pandas as pd
from app.market.provider.base_provider import BaseMarketDataProvider
from app.schemas.market.fdr import FdrIndexOhlcvRead

class MarketService:
    """
    _summary_
    시장 데이터 서비스 클래스

    _description_
    시장 지수, 종목 시세 등 시장 데이터를 조회하는 서비스 클래스입니다.
    데이터 소스는 BaseMarketDataProvider 구현체에 위임합니다.
    """
    
    # TODO: 추후에 WebSocket을 통한 실시간 데이터 수신 기능도 추가 필요
    
    def __init__(self, provider: BaseMarketDataProvider) -> None:
        self.provider = provider
    
    
    # ==============================================
    # 🛠️ 내부 메서드
    # ==============================================
    def _resolve_period(self, start: str | None, end: str | None, default_days: int) -> tuple[str, str]:
        now = datetime.datetime.now()
        if start is None:
            start = (now - datetime.timedelta(days=default_days)).strftime("%Y-%m-%d")
        if end is None:
            end = now.strftime("%Y-%m-%d")
        return start, end
    
    def _build_index_ohlcv(self, row: pd.Series, date: pd.Timestamp) -> FdrIndexOhlcvRead:
        return FdrIndexOhlcvRead(
            base_date=date.strftime("%Y-%m-%d"),
            open_price=str(row["Open"]),
            high_price=str(row["High"]),
            low_price=str(row["Low"]),
            close_price=str(row["Close"]),
            up_down=str(row["UpDown"]),
            change_amount=str(row["Comp"]),                        # 전일 대비 증감액
            change_rate=str(round(float(row["Change"]) * 100, 2)),  # 소수 → 퍼센트
            volume=str(row["Volume"]),
            trade_amount=str(row["Amount"]),
            market_cap=str(row["MarCap"]),
        )
    
    
    #==============================================
    # 🛠️ 서비스 메서드
    #==============================================
    
    # ⚙️ 특정 지수에 대한 OHLCV 데이터 조회. 가장 최근 데이터만 반환
    def get_index_ohlcv(self, index_code: str, start: str| None = None, end: str| None = None) -> FdrIndexOhlcvRead:
        # index code에 대한 정의가 필요함(index code가 아닌 종목코드는 별도의 서비스로 분리)
        
        # 넉넉잡아 2주로
        default_days = 14
        start, end = self._resolve_period(start, end, default_days=default_days)
        
        df = self.provider.get_ohlcv(index_code, start, end)
        if df is None or df.empty:
            raise ValueError(f"지수 코드 {index_code}에 대한 OHLCV 데이터를 조회할 수 없습니다.")
        
        return self._build_index_ohlcv(df.iloc[-1], df.index[-1])
    
    
    def get_market_summary(self) -> dict:
        """
        _summary_
        시장 요약 정보 조회

        _description_
        KOSPI, KOSDAQ, KOSPI200 등 주요 지수의 시세 요약 정보를 조회합니다.
        """
        summary = self.provider.get_market_summary()
        return summary