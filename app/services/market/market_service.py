from app.market.provider.base_provider import BaseMarketDataProvider

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
    
    
    # ⚙️ 특정 지수에 대한 OHLCV 데이터 조회
    def get_index_ohlcv(self, index_code: str, start: str| None = None, end: str| None = None):
        # index code에 대한 정의가 필요함(index code가 아닌 종목코드는 별도의 서비스로 분리)
        
        return self.provider.get_ohlcv(index_code, start, end)
    
    
    # ⚙️ 특정 종목에 대한 OHLCV 데이터 조회
    def get_stock_ohlcv(self, stock_code: str, start: str| None = None, end: str| None = None):
        return self.provider.get_ohlcv(stock_code, start, end)