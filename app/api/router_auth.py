from fastapi import APIRouter, Depends

from app.broker.kis.kis_auth import KISAuth
from app.schemas.kis import TokenResponse, ApprovalKeyResponse
from app.core.settings import settings


router = APIRouter()

def get_kis_auth() -> KISAuth:
    return KISAuth(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )

# TODO: 보안상 이 엔드포인트는 외부에 노출하지 않는 것이 좋을 듯. 추후에 인증된 사용자만 접근할 수 있도록 권한 체크 로직 추가 필요.
# KIS Access Token 발급
@router.post("/token", response_model=TokenResponse)
async def create_access_token(kis_auth: KISAuth = Depends(get_kis_auth)) -> TokenResponse:
    """
    KIS API로부터 access token을 발급받는 엔드포인트.
    """
    access_token = await kis_auth.get_access_token(endpoint="/oauth2/tokenP")
    
    return access_token

# KIS Websocket 인증키 발급
@router.post("/websocket", response_model=ApprovalKeyResponse)
async def create_websocket_approval_key(kis_auth: KISAuth = Depends(get_kis_auth)) -> ApprovalKeyResponse:
    """
    KIS API로부터 websocket approval key를 발급받는 엔드포인트.
    """
    approval_key = await kis_auth.get_websocket_approval_key(endpoint="/oauth2/Approval")
    
    return approval_key