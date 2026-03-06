from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Iterable, Optional

from ..transport import AsyncHTTPTransport


class AsyncChatCompletionsAPI:
    def __init__(self, transport: AsyncHTTPTransport) -> None:
        self._transport = transport

    async def create(
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
        return await self._transport.request(
            "POST",
            "/chat/completions",
            json_body=payload,
        )

    def stream(
        self,
        *,
        model: str,
        messages: Iterable[Dict[str, Any]],
        temperature: Optional[float] = None,
        **extra: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        payload.update(extra)

        return self._transport.stream("/chat/completions", json_body=payload)


class AsyncChatAPI:
    def __init__(self, transport: AsyncHTTPTransport) -> None:
        self.completions = AsyncChatCompletionsAPI(transport)
