class KISError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
        rt_cd: str | None = None,
        msg_cd: str | None = None,
        msg1: str | None = None,
        payload: dict | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        
        self.rt_cd = rt_cd
        self.msg_cd = msg_cd
        self.msg1 = msg1
        self.payload = payload
        
        super().__init__(message)


class KISAuthError(KISError):
    pass


class KISOrderError(KISError):
    pass

class KISAccountError(KISError):
    pass