from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Optional

from ..transport import AsyncHTTPTransport


class AsyncResponsesAPI:
    """Async variant of OpenAI Responses API compatible endpoint."""

    def __init__(self, transport: AsyncHTTPTransport) -> None:
        self._transport = transport

    async def create(
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
        return await self._transport.request(
            "POST",
            "/responses",
            json_body=payload,
        )

    def stream(
        self,
        *,
        model: str,
        input: Any,
        instructions: Optional[str] = None,
        **extra: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        payload: Dict[str, Any] = {
            "model": model,
            "input": input,
            "stream": True,
        }
        if instructions is not None:
            payload["instructions"] = instructions
        payload.update(extra)

        return self._transport.stream("/responses", json_body=payload)
