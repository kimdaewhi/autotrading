from decimal import Decimal, InvalidOperation
from typing import Any
from enum import Enum


def to_dict(data: Any) -> dict[str, Any]:
    """
    데이터에서 필요한 정보를 추출하여 딕셔너리 형태로 반환하는 유틸리티 함수.
    ex. Broker API 응답 객체
    """
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if hasattr(data, "model_dump"): # pydantic v2
        return data.model_dump()
    if hasattr(data, "dict"):       # pydantic v1
        return data.dict()
    if isinstance(data, Enum):
        return {"value": data.value}
    
    return {
        key: value
        for key, value in vars(data).items()
        if not key.startswith("_")
    }



def to_decimal(value: Any) -> Decimal | None:
    """
    값을 Decimal로 변환하는 유틸리티 함수.
    """
    if value in (None, "", "None"):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None