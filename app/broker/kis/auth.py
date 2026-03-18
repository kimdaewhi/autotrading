import httpx
from app.schemas.kis import TokenResponse, ApprovalKeyResponse
from app.utils.logger import get_logger
from app.core.exceptions import KisAuthError
from app.core.settings import settings

logger = get_logger(__name__)

class KISAuth:
    def __init__(self, appkey: str, appsecret: str, url: str = settings.kis_base_url) -> None:
        self.appkey = appkey
        self.appsecret = appsecret
        self.url = url
    
    
    
    # ⚙️ KIS API로부터 Access Token 발급 요청
    async def get_access_token(self, grant_type: str = "client_credentials", endpoint: str = "/oauth2/tokenP") -> TokenResponse:
        """
        KIS Access Token 발급 요청
        REQ : grant_type, appkey, appsecret
        RES : 
            access_token : string
            access_token_token_expired : string (yyyy-MM-dd HH:mm:ss)
            token_type : string(Bearer)
            expires_in : int(second)
        """
        auth_url = f"{self.url}{endpoint}"
        
        payload = {
            "grant_type": grant_type,
            "appkey": self.appkey,
            "appsecret": self.appsecret,
        }
        
        logger.info(f"Access Token 발급 요청 : {self.url}{endpoint}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url=auth_url,
                json=payload,
                headers={"Content-Type": "application/json;charset=utf-8"},
            )
        
        if resp.status_code != 200:
            try:
                error_body = resp.json()
            except Exception:
                error_body = {}

            error_code = error_body.get("error_code")
            error_desc = error_body.get("error_description", resp.text)

            logger.warning(f"토큰 발급 실패 | status={resp.status_code} | code={error_code} | message={error_desc}")

            raise KisAuthError(
                message=error_desc,
                status_code=resp.status_code,
                error_code=error_code,
            )
        
        data = resp.json()
        
        logger.info(f"Access Token 발급 성공. Token 만료일 : {data.get('access_token_token_expired')}")
        
        return TokenResponse(
            access_token=data.get("access_token"),
            access_token_token_expired=data.get("access_token_token_expired"),
            token_type=data.get("token_type"),
            expires_in=data.get("expires_in"),
        )
    
    
    
    # ⚙️ KIS API로부터 Websocket Approval Key 발급 요청
    async def get_websocket_approval_key(self, grant_type: str = "client_credentials", endpoint: str = "/oauth2/Approval") -> ApprovalKeyResponse:
        """
        KIS Websocket Approval Key 발급 요청
        REQ : grant_type, appkey, appsecret
        RES : approval_key : string
        """
        payload = {
            "grant_type": grant_type,
            "appkey": self.appkey,
            "secretkey": self.appsecret,
        }
        websocket_url = f"{self.url}{endpoint}"
        logger.info(f"Websocket 접속키 발급 요청 : {websocket_url}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url=websocket_url, 
                json=payload,
                headers={"Content-Type": "application/json;charset=utf-8"},
            )
        
        if resp.status_code != 200:
            try:
                error_body = resp.json()
            except Exception:
                error_body = {}

            error_code = error_body.get("error_code")
            error_desc = error_body.get("error_description", resp.text)

            logger.warning(
                f"Websocket 접속키 발급 실패 | status={resp.status_code} | code={error_code} | message={error_desc}"
            )

            raise KisAuthError(
                message=error_desc,
                status_code=resp.status_code,
                error_code=error_code,
            )
        
        data = resp.json()
        
        logger.info(f"Websocket 접속키 발급 성공.")
        
        return ApprovalKeyResponse(
            approval_key=data.get("approval_key"),
        )