from fastapi import APIRouter, Depends

from app.broker.kis.auth import KISAuth
from app.schemas.kis import TokenResponse
from app.core.settings import settings


router = APIRouter()

def get_kis_auth() -> KISAuth:
    return KISAuth(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        auth_url=f"{settings.kis_base_url}/oauth2/tokenP",
    )

@router.post("/token", response_model=TokenResponse)
async def create_access_token(kis_auth: KISAuth = Depends(get_kis_auth)) -> TokenResponse:
    """
    KIS API로부터 access token을 발급받는 엔드포인트.
    """
    access_token = await kis_auth.get_access_token()
    
    return access_token