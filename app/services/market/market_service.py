import datetime

import pandas as pd
from app.core.enums import MARKET_INDEX_CODE
from app.market.provider.base_provider import BaseMarketDataProvider
from app.schemas.market.fdr import FdrIndexOhlcvRead
from app.schemas.market.market import MarketIndexRead
from app.utils.logger import get_logger


logger = get_logger(__name__)
 
# 시장 요약에 노출할 지수 목록
SUMMARY_INDEX_CODES = (MARKET_INDEX_CODE.KOSPI, MARKET_INDEX_CODE.KOSDAQ)
 
# 지수 조회 기본 기간(일). 연휴를 감안해 넉넉히 잡는다.
DEFAULT_INDEX_PERIOD_DAYS = 14

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
    
    # ⚙️ 조회 기간 기본값 처리
    def _resolve_period(self, start: str | None, end: str | None, default_days: int) -> tuple[str, str]:
        now = datetime.datetime.now()
        if start is None:
            start = (now - datetime.timedelta(days=default_days)).strftime("%Y-%m-%d")
        if end is None:
            end = now.strftime("%Y-%m-%d")
        return start, end
    
    
    # ⚙️ FDR DataFrame 한 행 -> 원본 스키마
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
    
    
    # ⚙️ 원본 스키마 -> API 응답 스키마
    def _build_market_index(self, index_code: MARKET_INDEX_CODE, ohlcv: FdrIndexOhlcvRead) -> MarketIndexRead:
        return MarketIndexRead(
            name=index_code.name,
            base_date=ohlcv.base_date,
            close_price=ohlcv.close_price,
            change_amount=ohlcv.change_amount,
            change_rate=ohlcv.change_rate,
        )
    
    
    # ⚙️ 지수 조회 실패 흡수. 한쪽 지수 조회 실패 시 다른 지수 조회는 계속 진행
    def _try_get_index_ohlcv(self, index_code: MARKET_INDEX_CODE) -> FdrIndexOhlcvRead | None:
        try:
            return self.get_index_ohlcv(index_code.value)
        except Exception as e:
            logger.error(f"지수 {index_code.value} 조회 실패: {e}")
            return None
    
    
    # ⚙️ DataFrame 정규화. get_ohlcv 가 reset_index() 된 프레임을 주는 경우를 흡수
    def _normalize_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """ get_ohlcv 가 reset_index() 된 프레임을 주는 경우를 흡수한다. """
        frame = df.copy()
        if "Date" in frame.columns:
            frame = frame.set_index("Date")
        frame.index = pd.to_datetime(frame.index)
        return frame
    
    
    #==============================================
    # 🛠️ 서비스 메서드
    #==============================================
    
    # ⚙️ 특정 지수에 대한 OHLCV 데이터 조회. 가장 최근 데이터만 반환
    def get_index_ohlcv(self, index_code: str, start: str| None = None, end: str| None = None) -> FdrIndexOhlcvRead:
        start, end = self._resolve_period(start, end, default_days=DEFAULT_INDEX_PERIOD_DAYS)
        
        df = self.provider.get_ohlcv(index_code, start, end, use_cache=False)
        if df is None or df.empty:
            raise ValueError(f"지수 코드 {index_code}에 대한 OHLCV 데이터를 조회할 수 없습니다.")
        
        frame = self._normalize_frame(df)
        return self._build_index_ohlcv(frame.iloc[-1], frame.index[-1])
    
    
    # ⚙️ 시장 요약 정보 조회
    def get_market_summary(self) -> list[MarketIndexRead]:
        summary: list[MarketIndexRead] = []
        
        for index_code in SUMMARY_INDEX_CODES:
            ohlcv = self._try_get_index_ohlcv(index_code)
            if ohlcv is None:
                continue
            summary.append(self._build_market_index(index_code, ohlcv))
            
        return summary