from enum import StrEnum

class ORDER_TYPE(StrEnum):
    """
    주문 방식
    - 시장가 주문, 지정가 주문, 조건부 주문 등
    """
    MARKET = "market"               # 시장가 주문
    LIMIT = "limit"                 # 지정가 주문
    CONDITIONAL = "conditional"     # 조건부 주문

class ORDER_STATUS(StrEnum):
    """
    주문 상태
    - 주문의 현재 상태를 나타냄
    - DB 저장 시 status 필드에 저장되는 상태값
    """
    PENDING = "PENDING"                 # 보류
    PROCESSING = "PROCESSING"           # 진행
    REQUESTED = "REQUESTED"             # 요청
    FAILED = "FAILED"                   # 실패
    ACCEPTED = "ACCEPTED"               # 승인
    PARTIAL_FILLED = "PARTIAL_FILLED"   # 부분 체결
    FILLED = "FILLED"                   # 전체 체결
    CANCELED = "CANCELED"               # 취소


class ORDER_POSITION(StrEnum):
    """
    주문 방향
    - 매수, 매도 구분
    """
    BUY = "buy"     # 매수
    SELL = "sell"   # 매도