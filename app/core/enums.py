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
    TIMEOUT = "TIME_OUT"                 # 시간 초과로 인한 종료


class REBALANCE_STATUS(StrEnum):
    """
    리밸런싱 실행 상태
    - rebalances 테이블의 status 필드에 저장되는 상태값
    """
    RUNNING = "RUNNING"          # 실행 중
    COMPLETED = "COMPLETED"      # 정상 완료
    FAILED = "FAILED"            # 실패 (예외, orchestrator 실패 결과 등)
    

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





class REPORT_CODE(StrEnum):
    """
    DART 공시보고서 코드
     - 사업보고서, 반기보고서, 분기보고서 등
     - DART API에서 재무제표 조회 시 report_type에 매핑되는 코드값
     - 참고로, 공시보고서 종류는 더 다양하지만, 현재는 백테스트에 필요한 주요 보고서 4가지만 Enum으로 정의
     - 필요에 따라 추가 가능
    """
    ANNUAL = "11011",      # 사업보고서
    HALF = "11012",        # 반기보고서
    Q1 = "11013",          # 1분기보고서
    Q3 = "11014",          # 3분기보고서