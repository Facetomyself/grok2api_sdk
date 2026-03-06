from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional


VIDEO_URL_PATTERN = re.compile(
    r"https?://[^\s\"'>]+(?:\\.mp4|\\.webm|\\.mov|\\.m3u8)(?:\\?[^\s\"'>]*)?",
    re.IGNORECASE,
)
HTML_SOURCE_PATTERN = re.compile(r"src=[\"']([^\"']+)[\"']", re.IGNORECASE)
HTML_POSTER_PATTERN = re.compile(r"poster=[\"']([^\"']+)[\"']", re.IGNORECASE)


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


def extract_video_assets(response: Any) -> Dict[str, List[str]]:
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

    return {
        "videos": _dedupe(videos),
        "posters": _dedupe(posters),
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
