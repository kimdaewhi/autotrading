# base_filter.py
from abc import ABC, abstractmethod

import pandas as pd


class BaseFilter(ABC):
    """
    ⭐ 종목 필터링 베이스 클래스
    
    Screener가 생성한 유니버스를 입력받아 추가 조건으로 좁혀내는 역할.
    Screener와의 차이:
        - Screener: 전체 시장 → 유니버스 생성 (무 → 유)
        - Filter: 기존 유니버스 → 조건부 축소 (유 → 유')
    
    파이프라인 예시:
        [FScore Screener] → 50개 → [Valuation Filter] → 15개 → [Momentum Filter] → 최종 5~10개
    """

    @abstractmethod
    def filter(self, df_screened: pd.DataFrame) -> pd.DataFrame:
        """
        종목 코드 리스트를 입력받아 필터 조건을 적용한 결과를 반환
        
        Parameters
        ----------
        df_screened : Screener 또는 이전 Filter에서 넘어온 종목 데이터프레임
        
        Returns
        -------
        pd.DataFrame : 필터 조건을 통과한 종목 데이터프레임
        """
        pass