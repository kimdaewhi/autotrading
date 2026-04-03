from abc import ABC, abstractmethod
import pandas as pd


class BaseMarketDataProvider(ABC):
    """
    시장 데이터 제공자 인터페이스
        - get_stock_list: 전체 종목 리스트 조회
        - get_ohlcv: OHLCV 데이터 조회
        - 향후 필요에 따라 추가 메서드 정의 가능 (예: 재무제표, 뉴스 등)
        - 각 메서드는 pandas DataFrame을 반환하도록 설계
        - 예시 컬럼: code, name, market, open, high, low, close, volume 등
        - 구체적인 구현은 각 데이터 소스별로 다르게 작성 (예: FDR, Yahoo Finance 등)
        - 테스트 용이성을 위해 인터페이스를 명확히 정의
        - 실제 구현에서는 API 호출, 데이터 파싱 등의 로직이 포함될 예정
        - 에러 처리 및 예외 상황에 대한 고려도 필요 (예: 데이터 없음, API 오류 등)
        - 확장성을 고려하여 유연한 설계 권장
        - 문서화 및 주석을 통해 사용 방법과 반환 형식 명확히 설명
    """
    @abstractmethod
    def get_stock_list(self) -> pd.DataFrame:
        """
        전체 종목 리스트 조회
        columns 예시: [code, name, market]
        """
        pass

    @abstractmethod
    def get_ohlcv(self, code: str, start: str, end: str) -> pd.DataFrame:
        """
        OHLCV 데이터 조회
        """
        pass