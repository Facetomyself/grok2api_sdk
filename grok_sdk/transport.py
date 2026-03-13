from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional, Tuple, Union
from urllib.parse import urlparse

import requests
from requests import Response, Session

try:
    import httpx
except ImportError:  # pragma: no cover - handled at runtime
    httpx = None  # type: ignore[assignment]

from .config import SDKConfig
from .exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    ServerError,
    TimeoutError,
)
from .hooks import AsyncRequestLogHook, RequestLogEvent, RequestLogHook

MultipartFile = Tuple[str, Tuple[str, bytes, str]]


def _same_origin(left_url: str, right_url: str) -> bool:
    left = urlparse(left_url)
    right = urlparse(right_url)
    if not left.scheme or not right.scheme or not left.netloc or not right.netloc:
        return False
    return (
        left.scheme.lower() == right.scheme.lower()
        and (left.hostname or "").lower() == (right.hostname or "").lower()
        and _effective_port(left) == _effective_port(right)
    )


def _effective_port(parsed: Any) -> int:
    if parsed.port:
        return int(parsed.port)
    if parsed.scheme.lower() == "https":
        return 443
    return 80


def _extract_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message
        if isinstance(error, str):
            return error
        message = payload.get("message")
        if isinstance(message, str):
            return message
    return f"API request failed: {payload}"


class _RetryMixin:
    def __init__(self, config: SDKConfig) -> None:
        self.config = config

    def _max_attempts(self) -> int:
        return self.config.max_retries + 1

    @staticmethod
    def _should_retry_status(status_code: int) -> bool:
        return status_code in {408, 425, 429} or status_code >= 500

    def _compute_retry_delay(
        self, attempt: int, retry_after_header: Optional[str] = None
    ) -> float:
        if retry_after_header:
            parsed = self._parse_retry_after(retry_after_header)
            if parsed is not None:
                return min(self.config.retry_backoff_max, parsed)

        delay = self.config.retry_backoff_base * (2 ** (attempt - 1))
        return min(self.config.retry_backoff_max, delay)

    @staticmethod
    def _parse_retry_after(value: str) -> Optional[float]:
        try:
            return max(0.0, float(value.strip()))
        except ValueError:
            pass

        try:
            target = parsedate_to_datetime(value.strip())
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return max(0.0, (target - now).total_seconds())
        except (TypeError, ValueError):
            return None


class HTTPTransport(_RetryMixin):
    def __init__(
        self,
        config: SDKConfig,
        session: Optional[Session] = None,
        request_log_hook: Optional[RequestLogHook] = None,
    ) -> None:
        super().__init__(config)
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._request_log_hook = request_log_hook

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        url = self.config.build_url(path)
        max_attempts = self._max_attempts()

        for attempt in range(1, max_attempts + 1):
            start = time.monotonic()
            try:
                response = self._session.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json_body,
                    headers=self._build_headers(headers),
                    timeout=timeout if timeout is not None else self.config.timeout,
                    verify=self.config.verify_ssl,
                )
            except requests.Timeout as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method=method,
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                raise TimeoutError(f"Request timeout: {url}") from exc
            except requests.RequestException as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method=method,
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                raise APIError(f"Request failed: {exc}") from exc

            duration_ms = (time.monotonic() - start) * 1000.0
            if (
                self._should_retry_status(response.status_code)
                and attempt < max_attempts
            ):
                delay = self._compute_retry_delay(
                    attempt, response.headers.get("Retry-After")
                )
                self._emit_log(
                    phase="retry",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    retry_delay_s=delay,
                )
                response.close()
                time.sleep(delay)
                continue

            self._emit_log(
                phase="response",
                method=method,
                path=path,
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return self._parse_response(response)

        raise APIError("Request failed after retries exhausted")

    def request_form(
        self,
        method: str,
        path: str,
        *,
        data: Dict[str, Any],
        files: Optional[List[MultipartFile]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        url = self.config.build_url(path)
        max_attempts = self._max_attempts()

        for attempt in range(1, max_attempts + 1):
            start = time.monotonic()
            try:
                response = self._session.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    data=data,
                    files=files,
                    headers=self._build_headers(
                        headers,
                        include_json_content_type=False,
                    ),
                    timeout=timeout if timeout is not None else self.config.timeout,
                    verify=self.config.verify_ssl,
                )
            except requests.Timeout as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method=method,
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                raise TimeoutError(f"Request timeout: {url}") from exc
            except requests.RequestException as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method=method,
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                raise APIError(f"Request failed: {exc}") from exc

            duration_ms = (time.monotonic() - start) * 1000.0
            if (
                self._should_retry_status(response.status_code)
                and attempt < max_attempts
            ):
                delay = self._compute_retry_delay(
                    attempt, response.headers.get("Retry-After")
                )
                self._emit_log(
                    phase="retry",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    retry_delay_s=delay,
                )
                response.close()
                time.sleep(delay)
                continue

            self._emit_log(
                phase="response",
                method=method,
                path=path,
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return self._parse_response(response)

        raise APIError("Request failed after retries exhausted")

    def download(
        self,
        url: str,
        destination: Union[str, Path],
        *,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        overwrite: bool = True,
        skip_if_exists: bool = False,
        resume: bool = False,
        chunk_size: int = 1024 * 256,
        use_auth: Optional[bool] = None,
    ) -> Path:
        max_attempts = self._max_attempts()
        dest_path = Path(destination)
        if dest_path.exists() and dest_path.is_dir():
            raise IsADirectoryError(f"destination is a directory: {dest_path}")
        if skip_if_exists and dest_path.exists():
            return dest_path
        if dest_path.exists() and not overwrite and not resume:
            raise FileExistsError(f"destination exists: {dest_path}")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")

        attach_auth = (
            _same_origin(url, self.config.base_url)
            if use_auth is None
            else bool(use_auth)
        )
        request_headers: Dict[str, str] = {}
        if attach_auth and self.config.api_key:
            request_headers["Authorization"] = f"Bearer {self.config.api_key}"
        if headers:
            request_headers.update(headers)

        for attempt in range(1, max_attempts + 1):
            start = time.monotonic()
            current_size = (
                dest_path.stat().st_size if (resume and dest_path.exists()) else 0
            )
            request_headers_attempt = dict(request_headers)
            if resume and current_size > 0:
                request_headers_attempt["Range"] = f"bytes={current_size}-"
            try:
                with self._session.get(
                    url=url,
                    headers=request_headers_attempt,
                    timeout=timeout if timeout is not None else self.config.timeout,
                    verify=self.config.verify_ssl,
                    stream=True,
                ) as response:
                    duration_ms = (time.monotonic() - start) * 1000.0
                    if response.status_code == 416 and resume and dest_path.exists():
                        self._emit_log(
                            phase="response",
                            method="GET",
                            path=url,
                            url=url,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                        )
                        return dest_path

                    if (
                        self._should_retry_status(response.status_code)
                        and attempt < max_attempts
                    ):
                        delay = self._compute_retry_delay(
                            attempt, response.headers.get("Retry-After")
                        )
                        self._emit_log(
                            phase="retry",
                            method="GET",
                            path=url,
                            url=url,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                            retry_delay_s=delay,
                        )
                        time.sleep(delay)
                        continue

                    self._raise_for_status(response)
                    use_append_mode = (
                        resume and current_size > 0 and response.status_code == 206
                    )
                    if use_append_mode:
                        target_path = dest_path
                        write_mode = "ab"
                    else:
                        target_path = tmp_path
                        write_mode = "wb"

                    with target_path.open(write_mode) as file_obj:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                file_obj.write(chunk)
                    if target_path == tmp_path:
                        tmp_path.replace(dest_path)
                    self._emit_log(
                        phase="response",
                        method="GET",
                        path=url,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                    )
                    return dest_path
            except requests.Timeout as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method="GET",
                        path=url,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method="GET",
                    path=url,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                raise TimeoutError(f"Download timeout: {url}") from exc
            except requests.RequestException as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method="GET",
                        path=url,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method="GET",
                    path=url,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                raise APIError(f"Download failed: {exc}") from exc

        raise APIError("Download failed after retries exhausted")

    def stream(
        self,
        path: str,
        *,
        json_body: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        url = self.config.build_url(path)
        max_attempts = self._max_attempts()
        stream_headers = {"Accept": "text/event-stream"}
        if headers:
            stream_headers.update(headers)

        for attempt in range(1, max_attempts + 1):
            stream_started = False
            start = time.monotonic()
            try:
                with self._session.post(
                    url=url,
                    json=json_body,
                    headers=self._build_headers(stream_headers),
                    timeout=timeout if timeout is not None else self.config.timeout,
                    verify=self.config.verify_ssl,
                    stream=True,
                ) as response:
                    duration_ms = (time.monotonic() - start) * 1000.0
                    if (
                        self._should_retry_status(response.status_code)
                        and attempt < max_attempts
                    ):
                        delay = self._compute_retry_delay(
                            attempt, response.headers.get("Retry-After")
                        )
                        self._emit_log(
                            phase="retry",
                            method="POST",
                            path=path,
                            url=url,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                            retry_delay_s=delay,
                            is_stream=True,
                        )
                        time.sleep(delay)
                        continue

                    self._raise_for_status(response)
                    self._emit_log(
                        phase="response",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        is_stream=True,
                    )

                    for raw_line in response.iter_lines(decode_unicode=True):
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        stream_started = True
                        event_data = line[5:].strip()
                        if event_data == "[DONE]":
                            break
                        try:
                            yield json.loads(event_data)
                        except json.JSONDecodeError:
                            yield {"raw": event_data}
                    return
            except requests.Timeout as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts and not stream_started:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                        is_stream=True,
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method="POST",
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                    is_stream=True,
                )
                raise TimeoutError(f"Stream timeout: {url}") from exc
            except requests.RequestException as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts and not stream_started:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                        is_stream=True,
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method="POST",
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                    is_stream=True,
                )
                raise APIError(f"Stream request failed: {exc}") from exc

        raise APIError("Stream request failed after retries exhausted")

    def stream_form(
        self,
        path: str,
        *,
        data: Dict[str, Any],
        files: Optional[List[MultipartFile]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        url = self.config.build_url(path)
        max_attempts = self._max_attempts()
        stream_headers = {"Accept": "text/event-stream"}
        if headers:
            stream_headers.update(headers)

        for attempt in range(1, max_attempts + 1):
            stream_started = False
            start = time.monotonic()
            try:
                with self._session.post(
                    url=url,
                    data=data,
                    files=files,
                    headers=self._build_headers(
                        stream_headers,
                        include_json_content_type=False,
                    ),
                    timeout=timeout if timeout is not None else self.config.timeout,
                    verify=self.config.verify_ssl,
                    stream=True,
                ) as response:
                    duration_ms = (time.monotonic() - start) * 1000.0
                    if (
                        self._should_retry_status(response.status_code)
                        and attempt < max_attempts
                    ):
                        delay = self._compute_retry_delay(
                            attempt, response.headers.get("Retry-After")
                        )
                        self._emit_log(
                            phase="retry",
                            method="POST",
                            path=path,
                            url=url,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                            retry_delay_s=delay,
                            is_stream=True,
                        )
                        time.sleep(delay)
                        continue

                    self._raise_for_status(response)
                    self._emit_log(
                        phase="response",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        is_stream=True,
                    )

                    for raw_line in response.iter_lines(decode_unicode=True):
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        stream_started = True
                        event_data = line[5:].strip()
                        if event_data == "[DONE]":
                            break
                        try:
                            yield json.loads(event_data)
                        except json.JSONDecodeError:
                            yield {"raw": event_data}
                    return
            except requests.Timeout as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts and not stream_started:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                        is_stream=True,
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method="POST",
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                    is_stream=True,
                )
                raise TimeoutError(f"Stream timeout: {url}") from exc
            except requests.RequestException as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                if attempt < max_attempts and not stream_started:
                    delay = self._compute_retry_delay(attempt)
                    self._emit_log(
                        phase="retry",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                        is_stream=True,
                    )
                    time.sleep(delay)
                    continue
                self._emit_log(
                    phase="error",
                    method="POST",
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                    is_stream=True,
                )
                raise APIError(f"Stream request failed: {exc}") from exc

        raise APIError("Stream request failed after retries exhausted")

    def _build_headers(
        self,
        extra_headers: Optional[Dict[str, str]],
        *,
        include_json_content_type: bool = True,
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if include_json_content_type:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _parse_response(self, response: Response) -> Any:
        self._raise_for_status(response)
        if response.status_code == 204:
            return None

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.json()
        return {"text": response.text}

    def _raise_for_status(self, response: Response) -> None:
        if response.ok:
            return

        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": response.text}

        message = _extract_error_message(payload)
        status_code = response.status_code

        if status_code in {401, 403}:
            raise AuthenticationError(message, status_code=status_code, payload=payload)
        if status_code == 429:
            raise RateLimitError(message, status_code=status_code, payload=payload)
        if status_code >= 500:
            raise ServerError(message, status_code=status_code, payload=payload)
        raise APIError(message, status_code=status_code, payload=payload)

    def _emit_log(
        self,
        *,
        phase: str,
        method: str,
        path: str,
        url: str,
        attempt: int,
        max_attempts: int,
        status_code: Optional[int] = None,
        duration_ms: Optional[float] = None,
        retry_delay_s: Optional[float] = None,
        error: Optional[str] = None,
        is_stream: bool = False,
    ) -> None:
        if self._request_log_hook is None:
            return
        event = RequestLogEvent(
            transport="sync",
            phase=phase,
            method=method.upper(),
            path=path,
            url=url,
            attempt=attempt,
            max_attempts=max_attempts,
            status_code=status_code,
            duration_ms=duration_ms,
            retry_delay_s=retry_delay_s,
            error=error,
            is_stream=is_stream,
        )
        try:
            self._request_log_hook(event)
        except Exception:
            return


class AsyncHTTPTransport(_RetryMixin):
    def __init__(
        self,
        config: SDKConfig,
        client: Optional[Any] = None,
        request_log_hook: Optional[AsyncRequestLogHook] = None,
    ) -> None:
        if httpx is None:  # pragma: no cover - runtime guard
            raise RuntimeError(
                "httpx is required for AsyncHTTPTransport. Install with: pip install httpx"
            )
        super().__init__(config)
        self._client = client or httpx.AsyncClient(verify=self.config.verify_ssl)
        self._owns_client = client is None
        self._request_log_hook = request_log_hook

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        url = self.config.build_url(path)
        max_attempts = self._max_attempts()

        for attempt in range(1, max_attempts + 1):
            start = time.monotonic()
            try:
                response = await self._client.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json_body,
                    headers=self._build_headers(headers),
                    timeout=timeout if timeout is not None else self.config.timeout,
                )
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                timeout_exc = httpx is not None and isinstance(
                    exc, httpx.TimeoutException
                )
                request_exc = httpx is not None and isinstance(exc, httpx.RequestError)
                if (timeout_exc or request_exc) and attempt < max_attempts:
                    delay = self._compute_retry_delay(attempt)
                    await self._emit_log(
                        phase="retry",
                        method=method,
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                    continue
                await self._emit_log(
                    phase="error",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                if timeout_exc:
                    raise TimeoutError(f"Request timeout: {url}") from exc
                if request_exc:
                    raise APIError(f"Request failed: {exc}") from exc
                raise

            duration_ms = (time.monotonic() - start) * 1000.0
            if (
                self._should_retry_status(response.status_code)
                and attempt < max_attempts
            ):
                delay = self._compute_retry_delay(
                    attempt, response.headers.get("Retry-After")
                )
                await self._emit_log(
                    phase="retry",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    retry_delay_s=delay,
                )
                await asyncio.sleep(delay)
                continue

            await self._emit_log(
                phase="response",
                method=method,
                path=path,
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return self._parse_response(response)

        raise APIError("Request failed after retries exhausted")

    async def request_form(
        self,
        method: str,
        path: str,
        *,
        data: Dict[str, Any],
        files: Optional[List[MultipartFile]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        url = self.config.build_url(path)
        max_attempts = self._max_attempts()

        for attempt in range(1, max_attempts + 1):
            start = time.monotonic()
            try:
                response = await self._client.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    data=data,
                    files=files,
                    headers=self._build_headers(
                        headers,
                        include_json_content_type=False,
                    ),
                    timeout=timeout if timeout is not None else self.config.timeout,
                )
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                timeout_exc = httpx is not None and isinstance(
                    exc, httpx.TimeoutException
                )
                request_exc = httpx is not None and isinstance(exc, httpx.RequestError)
                if (timeout_exc or request_exc) and attempt < max_attempts:
                    delay = self._compute_retry_delay(attempt)
                    await self._emit_log(
                        phase="retry",
                        method=method,
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                    continue
                await self._emit_log(
                    phase="error",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                if timeout_exc:
                    raise TimeoutError(f"Request timeout: {url}") from exc
                if request_exc:
                    raise APIError(f"Request failed: {exc}") from exc
                raise

            duration_ms = (time.monotonic() - start) * 1000.0
            if (
                self._should_retry_status(response.status_code)
                and attempt < max_attempts
            ):
                delay = self._compute_retry_delay(
                    attempt, response.headers.get("Retry-After")
                )
                await self._emit_log(
                    phase="retry",
                    method=method,
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    retry_delay_s=delay,
                )
                await asyncio.sleep(delay)
                continue

            await self._emit_log(
                phase="response",
                method=method,
                path=path,
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return self._parse_response(response)

        raise APIError("Request failed after retries exhausted")

    async def download(
        self,
        url: str,
        destination: Union[str, Path],
        *,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        overwrite: bool = True,
        skip_if_exists: bool = False,
        resume: bool = False,
        chunk_size: int = 1024 * 256,
        use_auth: Optional[bool] = None,
    ) -> Path:
        max_attempts = self._max_attempts()
        dest_path = Path(destination)
        if dest_path.exists() and dest_path.is_dir():
            raise IsADirectoryError(f"destination is a directory: {dest_path}")
        if skip_if_exists and dest_path.exists():
            return dest_path
        if dest_path.exists() and not overwrite and not resume:
            raise FileExistsError(f"destination exists: {dest_path}")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")

        attach_auth = (
            _same_origin(url, self.config.base_url)
            if use_auth is None
            else bool(use_auth)
        )
        request_headers: Dict[str, str] = {}
        if attach_auth and self.config.api_key:
            request_headers["Authorization"] = f"Bearer {self.config.api_key}"
        if headers:
            request_headers.update(headers)

        for attempt in range(1, max_attempts + 1):
            start = time.monotonic()
            current_size = (
                dest_path.stat().st_size if (resume and dest_path.exists()) else 0
            )
            request_headers_attempt = dict(request_headers)
            if resume and current_size > 0:
                request_headers_attempt["Range"] = f"bytes={current_size}-"
            try:
                async with self._client.stream(
                    "GET",
                    url,
                    headers=request_headers_attempt,
                    timeout=timeout if timeout is not None else self.config.timeout,
                ) as response:
                    duration_ms = (time.monotonic() - start) * 1000.0
                    if response.status_code == 416 and resume and dest_path.exists():
                        await self._emit_log(
                            phase="response",
                            method="GET",
                            path=url,
                            url=url,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                        )
                        return dest_path

                    if (
                        self._should_retry_status(response.status_code)
                        and attempt < max_attempts
                    ):
                        delay = self._compute_retry_delay(
                            attempt, response.headers.get("Retry-After")
                        )
                        await self._emit_log(
                            phase="retry",
                            method="GET",
                            path=url,
                            url=url,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                            retry_delay_s=delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    self._raise_for_status(response)
                    use_append_mode = (
                        resume and current_size > 0 and response.status_code == 206
                    )
                    if use_append_mode:
                        target_path = dest_path
                        write_mode = "ab"
                    else:
                        target_path = tmp_path
                        write_mode = "wb"

                    with target_path.open(write_mode) as file_obj:
                        async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                            if chunk:
                                file_obj.write(chunk)
                    if target_path == tmp_path:
                        tmp_path.replace(dest_path)
                    await self._emit_log(
                        phase="response",
                        method="GET",
                        path=url,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                    )
                    return dest_path
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                timeout_exc = httpx is not None and isinstance(
                    exc, httpx.TimeoutException
                )
                request_exc = httpx is not None and isinstance(exc, httpx.RequestError)
                if (timeout_exc or request_exc) and attempt < max_attempts:
                    delay = self._compute_retry_delay(attempt)
                    await self._emit_log(
                        phase="retry",
                        method="GET",
                        path=url,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                    continue
                await self._emit_log(
                    phase="error",
                    method="GET",
                    path=url,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                if timeout_exc:
                    raise TimeoutError(f"Download timeout: {url}") from exc
                if request_exc:
                    raise APIError(f"Download failed: {exc}") from exc
                raise

        raise APIError("Download failed after retries exhausted")

    async def stream(
        self,
        path: str,
        *,
        json_body: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = self.config.build_url(path)
        max_attempts = self._max_attempts()
        stream_headers = {"Accept": "text/event-stream"}
        if headers:
            stream_headers.update(headers)

        for attempt in range(1, max_attempts + 1):
            stream_started = False
            start = time.monotonic()
            try:
                async with self._client.stream(
                    "POST",
                    url,
                    json=json_body,
                    headers=self._build_headers(stream_headers),
                    timeout=timeout if timeout is not None else self.config.timeout,
                ) as response:
                    duration_ms = (time.monotonic() - start) * 1000.0
                    if (
                        self._should_retry_status(response.status_code)
                        and attempt < max_attempts
                    ):
                        delay = self._compute_retry_delay(
                            attempt, response.headers.get("Retry-After")
                        )
                        await self._emit_log(
                            phase="retry",
                            method="POST",
                            path=path,
                            url=url,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                            retry_delay_s=delay,
                            is_stream=True,
                        )
                        await asyncio.sleep(delay)
                        continue

                    self._raise_for_status(response)
                    await self._emit_log(
                        phase="response",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        is_stream=True,
                    )

                    async for raw_line in response.aiter_lines():
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        stream_started = True
                        event_data = line[5:].strip()
                        if event_data == "[DONE]":
                            break
                        try:
                            yield json.loads(event_data)
                        except json.JSONDecodeError:
                            yield {"raw": event_data}
                    return
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                timeout_exc = httpx is not None and isinstance(
                    exc, httpx.TimeoutException
                )
                request_exc = httpx is not None and isinstance(exc, httpx.RequestError)
                if (
                    (timeout_exc or request_exc)
                    and attempt < max_attempts
                    and not stream_started
                ):
                    delay = self._compute_retry_delay(attempt)
                    await self._emit_log(
                        phase="retry",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                        is_stream=True,
                    )
                    await asyncio.sleep(delay)
                    continue
                await self._emit_log(
                    phase="error",
                    method="POST",
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                    is_stream=True,
                )
                if timeout_exc:
                    raise TimeoutError(f"Stream timeout: {url}") from exc
                if request_exc:
                    raise APIError(f"Stream request failed: {exc}") from exc
                raise

        raise APIError("Stream request failed after retries exhausted")

    async def stream_form(
        self,
        path: str,
        *,
        data: Dict[str, Any],
        files: Optional[List[MultipartFile]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = self.config.build_url(path)
        max_attempts = self._max_attempts()
        stream_headers = {"Accept": "text/event-stream"}
        if headers:
            stream_headers.update(headers)

        for attempt in range(1, max_attempts + 1):
            stream_started = False
            start = time.monotonic()
            try:
                async with self._client.stream(
                    "POST",
                    url,
                    data=data,
                    files=files,
                    headers=self._build_headers(
                        stream_headers,
                        include_json_content_type=False,
                    ),
                    timeout=timeout if timeout is not None else self.config.timeout,
                ) as response:
                    duration_ms = (time.monotonic() - start) * 1000.0
                    if (
                        self._should_retry_status(response.status_code)
                        and attempt < max_attempts
                    ):
                        delay = self._compute_retry_delay(
                            attempt, response.headers.get("Retry-After")
                        )
                        await self._emit_log(
                            phase="retry",
                            method="POST",
                            path=path,
                            url=url,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                            retry_delay_s=delay,
                            is_stream=True,
                        )
                        await asyncio.sleep(delay)
                        continue

                    self._raise_for_status(response)
                    await self._emit_log(
                        phase="response",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        is_stream=True,
                    )

                    async for raw_line in response.aiter_lines():
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        stream_started = True
                        event_data = line[5:].strip()
                        if event_data == "[DONE]":
                            break
                        try:
                            yield json.loads(event_data)
                        except json.JSONDecodeError:
                            yield {"raw": event_data}
                    return
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                timeout_exc = httpx is not None and isinstance(
                    exc, httpx.TimeoutException
                )
                request_exc = httpx is not None and isinstance(exc, httpx.RequestError)
                if (
                    (timeout_exc or request_exc)
                    and attempt < max_attempts
                    and not stream_started
                ):
                    delay = self._compute_retry_delay(attempt)
                    await self._emit_log(
                        phase="retry",
                        method="POST",
                        path=path,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        retry_delay_s=delay,
                        error=str(exc),
                        is_stream=True,
                    )
                    await asyncio.sleep(delay)
                    continue
                await self._emit_log(
                    phase="error",
                    method="POST",
                    path=path,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    duration_ms=duration_ms,
                    error=str(exc),
                    is_stream=True,
                )
                if timeout_exc:
                    raise TimeoutError(f"Stream timeout: {url}") from exc
                if request_exc:
                    raise APIError(f"Stream request failed: {exc}") from exc
                raise

        raise APIError("Stream request failed after retries exhausted")

    def _build_headers(
        self,
        extra_headers: Optional[Dict[str, str]],
        *,
        include_json_content_type: bool = True,
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if include_json_content_type:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _parse_response(self, response: Any) -> Any:
        self._raise_for_status(response)
        if response.status_code == 204:
            return None

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.json()
        return {"text": response.text}

    def _raise_for_status(self, response: Any) -> None:
        if 200 <= response.status_code < 300:
            return

        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": response.text}

        message = _extract_error_message(payload)
        status_code = response.status_code

        if status_code in {401, 403}:
            raise AuthenticationError(message, status_code=status_code, payload=payload)
        if status_code == 429:
            raise RateLimitError(message, status_code=status_code, payload=payload)
        if status_code >= 500:
            raise ServerError(message, status_code=status_code, payload=payload)
        raise APIError(message, status_code=status_code, payload=payload)

    async def _emit_log(
        self,
        *,
        phase: str,
        method: str,
        path: str,
        url: str,
        attempt: int,
        max_attempts: int,
        status_code: Optional[int] = None,
        duration_ms: Optional[float] = None,
        retry_delay_s: Optional[float] = None,
        error: Optional[str] = None,
        is_stream: bool = False,
    ) -> None:
        if self._request_log_hook is None:
            return
        event = RequestLogEvent(
            transport="async",
            phase=phase,
            method=method.upper(),
            path=path,
            url=url,
            attempt=attempt,
            max_attempts=max_attempts,
            status_code=status_code,
            duration_ms=duration_ms,
            retry_delay_s=retry_delay_s,
            error=error,
            is_stream=is_stream,
        )
        try:
            result = self._request_log_hook(event)
            if inspect.isawaitable(result):
                await result
        except Exception:
            return
