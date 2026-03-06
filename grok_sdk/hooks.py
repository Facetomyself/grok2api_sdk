from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union


@dataclass(frozen=True)
class RequestLogEvent:
    transport: str
    phase: str
    method: str
    path: str
    url: str
    attempt: int
    max_attempts: int
    status_code: Optional[int] = None
    duration_ms: Optional[float] = None
    retry_delay_s: Optional[float] = None
    error: Optional[str] = None
    is_stream: bool = False


RequestLogHook = Callable[[RequestLogEvent], None]
AsyncRequestLogHook = Callable[[RequestLogEvent], Union[None, Awaitable[None]]]
