from fastapi import APIRouter, Depends

from app.broker.kis.auth import KISAuth
from app.schemas.kis import TokenResponse, ApprovalKeyResponse
from app.core.settings import settings


router = APIRouter()

def get_kis_auth() -> KISAuth:
    return KISAuth(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )

@router.post("/token", response_model=TokenResponse)
async def create_access_token(kis_auth: KISAuth = Depends(get_kis_auth)) -> TokenResponse:
    """
    KIS API로부터 access token을 발급받는 엔드포인트.
    """
    token_url = f"{settings.kis_base_url}/oauth2/tokenP"
    access_token = await kis_auth.get_access_token(auth_url=token_url)
    
    return access_token


@router.post("/websocket", response_model=ApprovalKeyResponse)
async def create_websocket_approval_key(kis_auth: KISAuth = Depends(get_kis_auth)) -> ApprovalKeyResponse:
    """
    KIS API로부터 websocket approval key를 발급받는 엔드포인트.
    """
    approval_url = f"{settings.kis_base_url}/oauth2/Approval"
    approval_key = await kis_auth.get_websocket_approval_key(auth_url=approval_url)
    
    return approval_key