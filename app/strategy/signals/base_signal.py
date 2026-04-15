from abc import ABC, abstractmethod
import pandas as pd


class BaseSignal(ABC):
    """
    시그널 생성기 베이스 클래스
    
    OHLCV 데이터를 받아 종목별 BUY/SELL/HOLD 시그널을 생성하는 단위 모듈.
    MomentumStrategy, MACross, RSI 등이 이를 상속한다.
    백테스트에서도 직접 호출 가능.
    """

    @abstractmethod
    def generate_signal(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        복수 종목의 OHLCV 데이터 기반으로 매매 시그널 생성

        Args:
            data: {종목코드: OHLCV DataFrame} 딕셔너리
        Returns:
            pd.DataFrame: index=종목코드, columns=[signal, ...]
        """
        ...