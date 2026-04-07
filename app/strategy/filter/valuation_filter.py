# valuation_filter.py
"""
⭐ Valuation Filter
    * F-Score 등 퀄리티 스크리너를 통과한 종목 중 저평가 종목을 선별
    * PBR(주가순자산비율) 기준으로 저평가 종목을 필터링
    
    ☑️ 필터링 기준:
        - PBR(Price to Book Ratio) = 주가 / 주당순자산
        - PBR이 낮을수록 자산 대비 저평가된 종목
        - Piotroski 원논문에서도 F-Score + 저PBR 조합을 사용
    
    ☑️ 필터링 방식:
        - 입력 종목들의 PBR을 조회
        - PBR 오름차순 정렬 (낮을수록 저평가)
        - 상위 N개 종목 선정
    
    ⚠️ 주의사항:
        - PBR이 음수인 종목은 자본잠식 상태이므로 제외
        - PBR이 0인 종목은 데이터 오류 가능성이 있으므로 제외
"""

import pandas as pd

from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.filter.base_filter import BaseFilter
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ValuationFilter(BaseFilter):
    def __init__(self, top_n: int = 10, metric: str = "PBR"):
        """
        Parameters
        ----------
        top_n : 최종 선정 종목 수 (기본 15개)
        metric : 밸류에이션 지표 (기본 "PBR", 향후 "PER", "PSR" 등 확장 가능)
        """
        self.fdr_provider = FDRMarketDataProvider()
        self.top_n = top_n
        self.metric = metric
    
    
    def filter(self, df_screened: pd.DataFrame) -> pd.DataFrame:
        """
        종목 코드 리스트를 입력받아 PBR 기준 저평가 종목을 선별
        
        Parameters
        ----------
        codes : Screener에서 넘어온 종목 코드 리스트 (ex. F-Score 7점 이상 통과 종목)
        Returns
        -------
        list[str] : PBR 기준 저평가 상위 N개 종목 코드 리스트
        """
        logger.info(f"Valuation Filter 시작: {len(df_screened)}개 종목 (기준: {self.metric} 하위 {self.top_n}개)")
        
        # PBR > 0인 종목만 (자본잠식/데이터 오류 제외)
        df_valid = df_screened[df_screened[self.metric] > 0].copy()
        
        excluded = len(df_screened) - len(df_valid)
        if excluded > 0:
            logger.info(f"{self.metric} <= 0으로 {excluded}개 종목 제외")
        
        # 오름차순 정렬 후 상위 N개
        df_sorted = df_valid.sort_values(by=self.metric, ascending=True).head(self.top_n)
        
        logger.info(
            f"Valuation Filter 완료: {len(df_sorted)}개 종목 선정 "
            f"({self.metric} 범위: {df_sorted[self.metric].min():.2f} ~ {df_sorted[self.metric].max():.2f})"
        )
        
        return df_sorted