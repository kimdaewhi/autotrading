from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class KISResponseBase(BaseModel):
    rt_cd: str = Field(..., description="성공 실패 여부")
    msg_cd: str = Field(..., description="응답 코드")
    msg1: str = Field(..., description="응답 메시지")


class KISOutputResponse(KISResponseBase, Generic[T]):
    output: T | None = Field(default=None, description="응답 상세 데이터")