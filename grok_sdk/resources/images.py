from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple, Union

from ..transport import HTTPTransport, MultipartFile
from .media_utils import (
    collect_image_urls,
    ensure_bytes,
    guess_filename_from_url,
    normalize_form_bool,
    normalize_payload_urls,
)

ImageInput = Union[
    str, Path, bytes, bytearray, Tuple[str, bytes], Tuple[str, bytes, str]
]


class ImagesAPI:
    def __init__(self, transport: HTTPTransport) -> None:
        self._transport = transport

    def method(self) -> Any:
        result = self._transport.request("GET", "/images/method")
        return self._normalize_urls(result)

    def generate(
        self,
        *,
        prompt: str,
        model: str = "grok-imagine-1.0",
        n: int = 1,
        stream: bool = False,
        size: Optional[str] = None,
        concurrency: Optional[int] = None,
        response_format: Optional[str] = None,
        **extra: Any,
    ) -> Any:
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "stream": stream,
        }
        if size is not None:
            payload["size"] = size
        if concurrency is not None:
            payload["concurrency"] = concurrency
        if response_format is not None:
            payload["response_format"] = response_format
        payload.update(extra)

        if stream:
            return self._normalize_stream(
                self._transport.stream("/images/generations", json_body=payload)
            )
        result = self._transport.request(
            "POST", "/images/generations", json_body=payload
        )
        return self._normalize_urls(result)

    def stream_generate(
        self,
        *,
        prompt: str,
        model: str = "grok-imagine-1.0",
        n: int = 1,
        size: Optional[str] = None,
        concurrency: Optional[int] = None,
        response_format: Optional[str] = None,
        **extra: Any,
    ) -> Generator[Dict[str, Any], None, None]:
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "stream": True,
        }
        if size is not None:
            payload["size"] = size
        if concurrency is not None:
            payload["concurrency"] = concurrency
        if response_format is not None:
            payload["response_format"] = response_format
        payload.update(extra)
        return self._normalize_stream(
            self._transport.stream("/images/generations", json_body=payload)
        )

    def edit(
        self,
        *,
        prompt: str,
        images: Iterable[ImageInput],
        model: str = "grok-imagine-1.0-edit",
        n: int = 1,
        size: str = "1024x1024",
        quality: str = "standard",
        response_format: Optional[str] = None,
        style: Optional[str] = None,
        stream: bool = False,
        **extra: Any,
    ) -> Any:
        data = self._build_edit_form_data(
            prompt=prompt,
            model=model,
            n=n,
            size=size,
            quality=quality,
            response_format=response_format,
            style=style,
            stream=stream,
            extra=extra,
        )
        files = self._prepare_image_files(images)

        if stream:
            return self._normalize_stream(
                self._transport.stream_form(
                    "/images/edits",
                    data=data,
                    files=files,
                )
            )
        result = self._transport.request_form(
            "POST",
            "/images/edits",
            data=data,
            files=files,
        )
        return self._normalize_urls(result)

    def stream_edit(
        self,
        *,
        prompt: str,
        images: Iterable[ImageInput],
        model: str = "grok-imagine-1.0-edit",
        n: int = 1,
        size: str = "1024x1024",
        quality: str = "standard",
        response_format: Optional[str] = None,
        style: Optional[str] = None,
        **extra: Any,
    ) -> Generator[Dict[str, Any], None, None]:
        data = self._build_edit_form_data(
            prompt=prompt,
            model=model,
            n=n,
            size=size,
            quality=quality,
            response_format=response_format,
            style=style,
            stream=True,
            extra=extra,
        )
        files = self._prepare_image_files(images)
        return self._normalize_stream(
            self._transport.stream_form(
                "/images/edits",
                data=data,
                files=files,
            )
        )

    def extract_urls(self, response: Any) -> List[str]:
        normalized = self._normalize_urls(response)
        return collect_image_urls(normalized)

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

    def download_all(
        self,
        response: Any,
        output_dir: Union[str, Path],
        *,
        prefix: str = "image",
        overwrite: bool = True,
        skip_if_exists: bool = False,
        resume: bool = False,
    ) -> List[Path]:
        urls = self.extract_urls(response)
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)

        saved: List[Path] = []
        used_names: set[str] = set()
        for index, url in enumerate(urls, start=1):
            filename = guess_filename_from_url(
                url=url,
                prefix=prefix,
                index=index,
                default_ext=".jpg",
            )
            if filename in used_names:
                filename = f"{prefix}_{index}{Path(filename).suffix or '.jpg'}"
            used_names.add(filename)
            saved_path = self.download(
                url,
                directory / filename,
                overwrite=overwrite,
                skip_if_exists=skip_if_exists,
                resume=resume,
            )
            saved.append(saved_path)
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
    def _build_edit_form_data(
        *,
        prompt: str,
        model: str,
        n: int,
        size: str,
        quality: str,
        response_format: Optional[str],
        style: Optional[str],
        stream: bool,
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "prompt": prompt,
            "model": model,
            "n": str(n),
            "size": size,
            "quality": quality,
            "stream": normalize_form_bool(stream),
        }
        if response_format is not None:
            data["response_format"] = response_format
        if style is not None:
            data["style"] = style
        for key, value in extra.items():
            if value is None:
                continue
            if isinstance(value, bool):
                data[key] = normalize_form_bool(value)
            else:
                data[key] = str(value)
        return data

    @staticmethod
    def _prepare_image_files(images: Iterable[ImageInput]) -> List[MultipartFile]:
        files: List[MultipartFile] = []
        for index, item in enumerate(images):
            filename: str
            content: bytes
            content_type: str

            if isinstance(item, tuple):
                if len(item) == 2:
                    filename = str(item[0])
                    content = ensure_bytes(item[1], index=index)
                    guessed_type = mimetypes.guess_type(filename)[0]
                    content_type = guessed_type or "image/png"
                elif len(item) == 3:
                    filename = str(item[0])
                    content = ensure_bytes(item[1], index=index)
                    content_type = str(item[2])
                else:
                    raise TypeError(
                        "Tuple image input must be (filename, content) or "
                        "(filename, content, content_type)"
                    )
            elif isinstance(item, (str, Path)):
                path = Path(item)
                filename = path.name
                content = path.read_bytes()
                guessed_type = mimetypes.guess_type(path.name)[0]
                content_type = guessed_type or "image/png"
            else:
                filename = f"image_{index + 1}.png"
                content = ensure_bytes(item, index=index)
                content_type = "image/png"

            files.append(("image", (filename, content, content_type)))

        if not files:
            raise ValueError("images cannot be empty")
        return files
