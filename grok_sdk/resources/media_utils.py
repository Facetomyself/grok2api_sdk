from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse


VIDEO_URL_PATTERN = re.compile(
    r"https?://[^\s\"'>]+(?:\\.mp4|\\.webm|\\.mov|\\.m3u8)(?:\\?[^\s\"'>]*)?",
    re.IGNORECASE,
)
HTML_SOURCE_PATTERN = re.compile(r"src=[\"']([^\"']+)[\"']", re.IGNORECASE)
HTML_POSTER_PATTERN = re.compile(r"poster=[\"']([^\"']+)[\"']", re.IGNORECASE)
URL_IN_TEXT_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


def build_video_messages(
    *,
    prompt: Optional[str],
    messages: Optional[Iterable[Dict[str, Any]]],
    image_url: Optional[str],
) -> List[Dict[str, Any]]:
    if messages is not None:
        resolved = list(messages)
        if not resolved:
            raise ValueError("messages cannot be empty")
        return resolved

    if not prompt or not prompt.strip():
        raise ValueError("prompt is required when messages is not provided")

    if image_url:
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
    return [{"role": "user", "content": prompt}]


def extract_video_assets(
    response: Any, *, public_base_url: Optional[str] = None
) -> Dict[str, List[str]]:
    content = _extract_message_content(response)
    if not content:
        return {"videos": [], "posters": []}

    videos: List[str] = []
    posters: List[str] = []

    for match in HTML_SOURCE_PATTERN.finditer(content):
        videos.append(match.group(1))
    for match in HTML_POSTER_PATTERN.finditer(content):
        posters.append(match.group(1))
    for match in VIDEO_URL_PATTERN.finditer(content):
        videos.append(match.group(0))

    deduped_videos = _dedupe(videos)
    deduped_posters = _dedupe(posters)

    if public_base_url:
        deduped_videos = [normalize_url(item, public_base_url) for item in deduped_videos]
        deduped_posters = [normalize_url(item, public_base_url) for item in deduped_posters]

    return {
        "videos": deduped_videos,
        "posters": deduped_posters,
    }


def _extract_message_content(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def normalize_form_bool(value: bool) -> str:
    return "true" if value else "false"


def ensure_bytes(value: Any, *, index: int) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str) or isinstance(value, Path):
        return Path(value).read_bytes()
    raise TypeError(f"Unsupported image input at index {index}: {type(value)!r}")


def normalize_url(url: str, public_base_url: str) -> str:
    target = urlparse(url)
    if target.scheme not in {"http", "https"} or not target.netloc:
        return url

    host = (target.hostname or "").strip().lower()
    if host not in LOOPBACK_HOSTS:
        return url

    base = urlparse(public_base_url)
    if base.scheme not in {"http", "https"} or not base.netloc:
        return url

    rewritten = target._replace(scheme=base.scheme, netloc=base.netloc)
    return urlunparse(rewritten)


def normalize_urls_in_text(text: str, public_base_url: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return normalize_url(match.group(0), public_base_url)

    return URL_IN_TEXT_PATTERN.sub(_replace, text)


def normalize_payload_urls(payload: Any, public_base_url: str) -> Any:
    if isinstance(payload, dict):
        return {
            key: normalize_payload_urls(value, public_base_url)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [normalize_payload_urls(item, public_base_url) for item in payload]
    if isinstance(payload, str):
        return normalize_urls_in_text(payload, public_base_url)
    return payload


def collect_image_urls(response: Any) -> List[str]:
    if not isinstance(response, dict):
        return []
    data = response.get("data")
    if not isinstance(data, list):
        return []

    urls: List[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if isinstance(url, str) and url.strip():
            urls.append(url)
    return _dedupe(urls)


def guess_filename_from_url(
    *,
    url: str,
    prefix: str,
    index: int,
    default_ext: str,
) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name if parsed.path else ""
    if name and Path(name).suffix:
        return name
    return f"{prefix}_{index}{default_ext}"
