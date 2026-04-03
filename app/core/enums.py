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
    # 취소(단순 취소만이 아닌, 해당 주문이 더이상 유효하지 않는 모든 상태 포함)
    # ex. 
    # - 전량 취소
    # - 일부 체결 후 취소
    # - 전량 정정 후 정정 주문 전량 체결
    # - 일부 체결 후 정정 주문 전량 체결
    # - 이 외에도, 주문이 더이상 유효하지 않게 되는 모든 경우(예: 정정 주문으로 인해 부모 주문이 대체된 경우) 포함
    #
    # NOTE:
    # - 주로 "부모 주문" 종료 정책에 사용한다.
    # - 정정 자식 주문 자체가 전량 체결된 경우 자식은 FILLED로 관리
    CANCELED = "CANCELED"
    
    # -------- 현재 쓰지않지만 향후 필요할 수 있는 상태 --------
    PARTIAL_CANCELED = "PARTIAL_CANCELED" # 부분 취소(일부 체결 후 취소)
    REPLACED = "REPLACED"                 # 정정(정정 주문으로 인한 부모 주문이 대체된 상태, 더이상 유효하지 않은 주문)
    FINALIZING = "FINALIZING"             # 체결 및 정합성 검증중


class ORDER_ACTION(StrEnum):
    """
    주문 방향
    - 매수, 매도 구분
    """
    BUY = "buy"     # 매수
    SELL = "sell"   # 매도
    CANCEL = "cancel" # 취소
    MODIFY = "modify" # 정정

class ORDER_KIND(StrEnum):
    """
    주문 종류
    - 신규 주문, 정정 주문, 취소 주문
    """
    NEW = "new"         # 신규 주문
    MODIFY = "modify"   # 정정 주문
    CANCEL = "cancel"   # 취소 주문



class STRATEGY_SIGNAL(StrEnum):
    """
    전략 신호
    - 전략에서 생성되는 신호의 종류를 나타냄
    """
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"