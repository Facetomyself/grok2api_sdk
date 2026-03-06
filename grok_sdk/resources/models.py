from __future__ import annotations

from typing import Any

from ..transport import HTTPTransport


class ModelsAPI:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def list(self) -> Any:
        return self._transport.request("GET", "/models")

    def retrieve(self, model_id: str) -> Any:
        return self._transport.request("GET", f"/models/{model_id}")
