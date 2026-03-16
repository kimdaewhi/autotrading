from pydantic import BaseModel
from typing import Optional


class TokenResponse(BaseModel):
    access_token: str
    access_token_token_expired: Optional[str]
    token_type: str
    expires_in: int