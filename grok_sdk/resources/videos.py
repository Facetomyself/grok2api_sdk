from __future__ import annotations

from typing import Any, Dict, Generator, Iterable, List, Optional

from ..transport import HTTPTransport
from .media_utils import build_video_messages, extract_video_assets


class VideosAPI:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def generate(
        self,
        *,
        model: str = "grok-imagine-1.0-video",
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        image_url: Optional[str] = None,
        stream: bool = False,
        aspect_ratio: str = "3:2",
        video_length: int = 6,
        resolution: str = "SD",
        preset: str = "normal",
        thinking: Optional[str] = None,
        request_timeout: float = 180.0,
        **extra: Any,
    ) -> Any:
        payload = self._build_payload(
            model=model,
            prompt=prompt,
            messages=messages,
            image_url=image_url,
            stream=stream,
            aspect_ratio=aspect_ratio,
            video_length=video_length,
            resolution=resolution,
            preset=preset,
            thinking=thinking,
            extra=extra,
        )
        if stream:
            return self._transport.stream(
                "/chat/completions",
                json_body=payload,
                timeout=request_timeout,
            )
        return self._transport.request(
            "POST",
            "/chat/completions",
            json_body=payload,
            timeout=request_timeout,
        )

    def stream(
        self,
        *,
        model: str = "grok-imagine-1.0-video",
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        image_url: Optional[str] = None,
        aspect_ratio: str = "3:2",
        video_length: int = 6,
        resolution: str = "SD",
        preset: str = "normal",
        thinking: Optional[str] = None,
        request_timeout: float = 180.0,
        **extra: Any,
    ) -> Generator[Dict[str, Any], None, None]:
        payload = self._build_payload(
            model=model,
            prompt=prompt,
            messages=messages,
            image_url=image_url,
            stream=True,
            aspect_ratio=aspect_ratio,
            video_length=video_length,
            resolution=resolution,
            preset=preset,
            thinking=thinking,
            extra=extra,
        )
        return self._transport.stream(
            "/chat/completions",
            json_body=payload,
            timeout=request_timeout,
        )

    @staticmethod
    def extract_assets(response: Any) -> Dict[str, List[str]]:
        return extract_video_assets(response)

    @staticmethod
    def _build_payload(
        *,
        model: str,
        prompt: Optional[str],
        messages: Optional[Iterable[Dict[str, Any]]],
        image_url: Optional[str],
        stream: bool,
        aspect_ratio: str,
        video_length: int,
        resolution: str,
        preset: str,
        thinking: Optional[str],
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": build_video_messages(
                prompt=prompt,
                messages=messages,
                image_url=image_url,
            ),
            "stream": stream,
            "video_config": {
                "aspect_ratio": aspect_ratio,
                "video_length": video_length,
                "resolution": resolution,
                "preset": preset,
            },
        }
        if thinking is not None:
            payload["thinking"] = thinking
        payload.update(extra)
        return payload
