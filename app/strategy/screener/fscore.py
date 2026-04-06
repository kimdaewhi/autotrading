"""
⭐ F-Score Screener
    * 스크리닝을 통한 유니버스 선정 모델
    * 재무 데이터 기반의 퀄리티 스코어링
    * Piotroski F-Score를 활용하여 기업의 재무 건전성과 성장성을 평가
    * 각 지표가 우수할 경우 1점, 그렇지 않으면 0점으로 평가하여 총 9점 만점의 F-Score 산출

☑️ Scoring에 사용되는 지표 대분류
    - Profitability : 수익성
    - Financial Performance : 재무 성과
    - Operating Efficiency : 영업 효율성
    - 이하 수익성 항목은 P, 재무 성과는 F, 영업 효율성은 O로 표기
    
    * F-Score = F_ROA + F_CFO + F_ΔROA + F_ACCRUAL + F_ΔLEVER + F_ΔLIQUID + F_EQ_OFFER + F_ΔMARGIN + F_ΔTURNOVER
    * 산출 방법 설명 : 
        - (P) F_ROA : ROA가 양수이면 1점, 그렇지 않으면 0점
        - (P) F_CFO : 영업활동현금흐름이 양수이면 1점, 그렇지 않으면 0점
        - (P) F_ΔROA : ROA의 변화가 양수이면 1점, 그렇지 않으면 0점
        - (P) F_ACCRUAL : CFO/총자산이 ROA보다 크면 1점, 그렇지 않으면 0점(의미 : 이익이 실제 현금흐름에 기반한 것인지 평가)
        - (F) F_ΔLEVER : 부채비율의 변화가 음수이면 1점, 그렇지 않으면 0점
        - (F) F_ΔLIQUID : 유동비율의 변화가 양수이면 1점, 그렇지 않으면 0점
        - (F) F_EQ_OFFER : 주식 발행이 없는 경우 1점, 그렇지 않으면 0점(ex. 유상증자 등으로 인해 주식 수가 증가한 경우 0점)
        - (O) F_ΔMARGIN : 매출총이익률의 변화가 양수이면 1점, 그렇지 않으면 0점
        - (O) F_ΔTURNOVER : 자산회전율의 변화가 양수이면 1점, 그렇지 않으면 0점(의미 : 자산을 얼마나 효율적으로 활용하여 매출을 창출했는지 평가)
    
"""

