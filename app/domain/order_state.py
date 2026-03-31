from typing import Dict, Set

from app.core.enums import ORDER_STATUS

ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    ORDER_STATUS.PENDING.value: {
        ORDER_STATUS.PROCESSING.value,
        ORDER_STATUS.FAILED.value,
    },

    ORDER_STATUS.PROCESSING.value: {
        ORDER_STATUS.REQUESTED.value,
        ORDER_STATUS.ACCEPTED.value,
        ORDER_STATUS.FAILED.value,
        ORDER_STATUS.PENDING.value,  # rate limit 초과 등으로 일시적으로 상태를 되돌릴 수 있음
    },

    ORDER_STATUS.REQUESTED.value: {
        ORDER_STATUS.REQUESTED.value,
        ORDER_STATUS.ACCEPTED.value,
        ORDER_STATUS.PARTIAL_FILLED.value,
        ORDER_STATUS.FILLED.value,
        ORDER_STATUS.CANCELED.value,
        ORDER_STATUS.FAILED.value,
    },

    ORDER_STATUS.ACCEPTED.value: {
        ORDER_STATUS.ACCEPTED.value,
        ORDER_STATUS.PARTIAL_FILLED.value,
        ORDER_STATUS.FILLED.value,
        ORDER_STATUS.CANCELED.value,
        ORDER_STATUS.FAILED.value,
    },

    ORDER_STATUS.PARTIAL_FILLED.value: {
        ORDER_STATUS.PARTIAL_FILLED.value,
        ORDER_STATUS.FILLED.value,
        ORDER_STATUS.CANCELED.value,
        ORDER_STATUS.FAILED.value,
    },
}

TERMINAL_STATES: Set[str] = {
    ORDER_STATUS.FILLED.value,
    ORDER_STATUS.CANCELED.value,
    ORDER_STATUS.FAILED.value,
}


# ⚙️ 주문 상태 전이 가능 여부 판단 함수
def can_transition(current_status: str, next_status: str) -> bool:
    if current_status == next_status:
        return True
    
    if current_status in TERMINAL_STATES:
        return False
    
    allowed_next_statuses = ALLOWED_TRANSITIONS.get(current_status, set())
    return next_status in allowed_next_statuses