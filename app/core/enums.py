from enum import StrEnum

class OrderType(StrEnum):
    """
    주문 방식
    - 시장가 주문, 지정가 주문, 조건부 주문 등
    """
    MARKET = "market"               # 시장가 주문
    LIMIT = "limit"                 # 지정가 주문
    CONDITIONAL = "conditional"     # 조건부 주문