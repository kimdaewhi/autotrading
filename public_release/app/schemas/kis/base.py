from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")
T1 = TypeVar("T1")
T2 = TypeVar("T2")

class KISResponseBase(BaseModel):
    rt_cd: str = Field(..., description="성공 실패 여부")
    msg_cd: str = Field(..., description="응답 코드")
    msg1: str = Field(..., description="응답 메시지")


class KISOutputResponse(KISResponseBase, Generic[T]):
    output: T | None = Field(default=None, description="응답 상세 데이터")


class KISMultiOutputResponse(KISResponseBase, Generic[T1, T2]):
    ctx_area_fk100: str = Field(..., description="연속조회검색조건100")
    ctx_area_nk100: str = Field(..., description="연속조회키100")
    output1: T1 | None = Field(default=None, description="응답 상세 데이터 1")
    output2: T2 | None = Field(default=None, description="응답 상세 데이터 2")