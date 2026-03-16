from app.schemas.kis import TokenResponse
import httpx


class KISAuth:
    def __init__(self, appkey: str, appsecret: str, auth_url: str = "https://openapi.koreainvestment.com:29443/oauth2/tokenP") -> None:
        """
        appkey, appsecret는 외부 주입.
        auth_url은 실제 토큰 발급 endpoint로, 필요에 따라 모의투자/실전투자 구분에 따라 달라질 수 있음.
        """
        self.appkey = appkey
        self.appsecret = appsecret
        self.auth_url = auth_url
        
        
    async def get_access_token(self, grant_type: str = "client_credentials") -> TokenResponse:
        """
        REQ : grant_type, appkey, appsecret
        RES : access_token, access_token_token_expired, token_type, expires_in
        """
        payload = {
            "grant_type": grant_type,
            "appkey": self.appkey,
            "appsecret": self.appsecret,
        }
    
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url=self.auth_url, 
                json=payload,
                headers={"Content-Type": "application/json;charset=utf-8"},
            )
        
        if resp.status_code != 200:
            raise Exception(f"Failed to get access token: {resp.status_code} - {resp.text}")
        
        data = resp.json()
        
        return TokenResponse(
            access_token=data.get("access_token"),
            access_token_token_expired=data.get("access_token_token_expired"),
            token_type=data.get("token_type"),
            expires_in=data.get("expires_in"),
        )