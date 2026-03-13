from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from ..transport import AsyncHTTPTransport


class AsyncOpenAIVideosAPI:
    def __init__(self, transport: AsyncHTTPTransport) -> None:
        self._transport = transport

    async def create(
        self,
        *,
        model: str,
        prompt: str,
        size: Optional[str] = None,
        seconds: Optional[int] = None,
        quality: Optional[str] = None,
        image_reference: Optional[Union[str, Dict[str, Any]]] = None,
        **extra: Any,
    ) -> Any:
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
        }
        if size is not None:
            payload["size"] = size
        if seconds is not None:
            payload["seconds"] = seconds
        if quality is not None:
            payload["quality"] = quality
        if image_reference is not None:
            payload["image_reference"] = image_reference
        payload.update(extra)

        return await self._transport.request(
            "POST",
            "/videos",
            json_body=payload,
        )

    async def create_with_image_file(
        self,
        *,
        model: str,
        prompt: str,
        image_path: Union[str, Path],
        size: Optional[str] = None,
        seconds: Optional[int] = None,
        quality: Optional[str] = None,
        **extra: Any,
    ) -> Any:
        path = Path(image_path)
        data: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
        }
        if size is not None:
            data["size"] = size
        if seconds is not None:
            data["seconds"] = str(seconds)
        if quality is not None:
            data["quality"] = quality
        for k, v in extra.items():
            if v is None:
                continue
            data[k] = str(v) if not isinstance(v, bool) else ("true" if v else "false")

        files = [("input_reference", (path.name, path.read_bytes(), "image/png"))]
        return await self._transport.request_form(
            "POST",
            "/videos",
            data=data,
            files=files,
        )
