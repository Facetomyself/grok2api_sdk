from __future__ import annotations

from typing import Any, Optional


class GrokSDKError(Exception):
    pass


class APIError(GrokSDKError):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        payload: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class AuthenticationError(APIError):
    pass


class RateLimitError(APIError):
    pass


class ServerError(APIError):
    pass


class TimeoutError(GrokSDKError):
    pass
