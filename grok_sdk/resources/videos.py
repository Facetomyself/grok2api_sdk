from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Union

from ..transport import HTTPTransport
from .media_utils import (
    build_video_messages,
    extract_video_assets,
    guess_filename_from_url,
    normalize_payload_urls,
)


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
            return self._normalize_stream(
                self._transport.stream(
                    "/chat/completions",
                    json_body=payload,
                    timeout=request_timeout,
                )
            )
        result = self._transport.request(
            "POST",
            "/chat/completions",
            json_body=payload,
            timeout=request_timeout,
        )
        return self._normalize_urls(result)

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
        return self._normalize_stream(
            self._transport.stream(
                "/chat/completions",
                json_body=payload,
                timeout=request_timeout,
            )
        )

    def extract_assets(self, response: Any) -> Dict[str, List[str]]:
        return extract_video_assets(
            response,
            public_base_url=self._transport.config.base_url,
        )

    def download(
        self,
        url: str,
        destination: Union[str, Path],
        *,
        overwrite: bool = True,
        skip_if_exists: bool = False,
        resume: bool = False,
    ) -> Path:
        normalized = self._normalize_urls(url)
        normalized_url = normalized if isinstance(normalized, str) else url
        return self._transport.download(
            normalized_url,
            destination,
            overwrite=overwrite,
            skip_if_exists=skip_if_exists,
            resume=resume,
        )

    def download_assets(
        self,
        response: Any,
        output_dir: Union[str, Path],
        *,
        download_videos: bool = True,
        download_posters: bool = True,
        overwrite: bool = True,
        skip_if_exists: bool = False,
        resume: bool = False,
    ) -> Dict[str, List[Path]]:
        assets = self.extract_assets(response)
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        saved: Dict[str, List[Path]] = {"videos": [], "posters": []}

        if download_videos:
            for index, url in enumerate(assets.get("videos", []), start=1):
                filename = guess_filename_from_url(
                    url=url,
                    prefix="video",
                    index=index,
                    default_ext=".mp4",
                )
                saved["videos"].append(
                    self.download(
                        url,
                        directory / filename,
                        overwrite=overwrite,
                        skip_if_exists=skip_if_exists,
                        resume=resume,
                    )
                )

        if download_posters:
            for index, url in enumerate(assets.get("posters", []), start=1):
                filename = guess_filename_from_url(
                    url=url,
                    prefix="poster",
                    index=index,
                    default_ext=".jpg",
                )
                saved["posters"].append(
                    self.download(
                        url,
                        directory / filename,
                        overwrite=overwrite,
                        skip_if_exists=skip_if_exists,
                        resume=resume,
                    )
                )

        return saved

    def _normalize_urls(self, payload: Any) -> Any:
        return normalize_payload_urls(payload, self._transport.config.base_url)

    def _normalize_stream(
        self, source: Generator[Dict[str, Any], None, None]
    ) -> Generator[Dict[str, Any], None, None]:
        for chunk in source:
            normalized = self._normalize_urls(chunk)
            yield normalized if isinstance(normalized, dict) else chunk

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
