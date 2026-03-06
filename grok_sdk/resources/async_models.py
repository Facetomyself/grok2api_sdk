from __future__ import annotations

from typing import Any

from ..transport import AsyncHTTPTransport


class AsyncModelsAPI:
    def __init__(self, transport: AsyncHTTPTransport) -> None:
        self._transport = transport

    async def list(self) -> Any:
        return await self._transport.request("GET", "/models")

    async def retrieve(self, model_id: str) -> Any:
        return await self._transport.request("GET", f"/models/{model_id}")
