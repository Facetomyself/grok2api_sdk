from __future__ import annotations

from typing import Any, Dict, Generator, Optional

from ..transport import HTTPTransport


class ResponsesAPI:
    """OpenAI Responses API compatible endpoint.

    grok2api implements a /v1/responses endpoint that is compatible with
    OpenAI's Responses API.

    See: https://github.com/chenyme/grok2api
    """

    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def create(
        self,
        *,
        model: str,
        input: Any,
        instructions: Optional[str] = None,
        stream: bool = False,
        **extra: Any,
    ) -> Any:
        payload: Dict[str, Any] = {
            "model": model,
            "input": input,
            "stream": stream,
        }
        if instructions is not None:
            payload["instructions"] = instructions
        payload.update(extra)

        if stream:
            return self._transport.stream("/responses", json_body=payload)
        return self._transport.request("POST", "/responses", json_body=payload)

    def stream(
        self,
        *,
        model: str,
        input: Any,
        instructions: Optional[str] = None,
        **extra: Any,
    ) -> Generator[Dict[str, Any], None, None]:
        payload: Dict[str, Any] = {
            "model": model,
            "input": input,
            "stream": True,
        }
        if instructions is not None:
            payload["instructions"] = instructions
        payload.update(extra)

        return self._transport.stream("/responses", json_body=payload)
