class KisAuthError(Exception):
    def __init__(self, message: str, status_code: int | None = None, error_code: str | None = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)