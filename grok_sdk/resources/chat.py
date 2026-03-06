from __future__ import annotations

from typing import Any, Dict, Generator, Iterable, Optional

from ..transport import HTTPTransport


class ChatCompletionsAPI:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def create(
        self,
        *,
        model: str,
        messages: Iterable[Dict[str, Any]],
        temperature: Optional[float] = None,
        stream: bool = False,
        **extra: Any,
    ) -> Any:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        payload.update(extra)

        if stream:
            return self._transport.stream("/chat/completions", json_body=payload)
        return self._transport.request("POST", "/chat/completions", json_body=payload)

    def stream(
        self,
        *,
        model: str,
        messages: Iterable[Dict[str, Any]],
        temperature: Optional[float] = None,
        **extra: Any,
    ) -> Generator[Dict[str, Any], None, None]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        payload.update(extra)

        return self._transport.stream("/chat/completions", json_body=payload)


class ChatAPI:
    def __init__(self, transport: HTTPTransport) -> None:
        self.completions = ChatCompletionsAPI(transport)
