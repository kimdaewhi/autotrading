from pydantic import BaseModel


class KillSwitchStateResponse(BaseModel):
    enabled: bool
    message: str


class KillSwitchUpdateRequest(BaseModel):
    enabled: bool