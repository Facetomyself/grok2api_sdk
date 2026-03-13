from __future__ import annotations

from dataclasses import dataclass
from typing import Generator, Iterable, List, Optional


@dataclass
class SSEEvent:
    event: Optional[str]
    data: str
    id: Optional[str] = None
    retry: Optional[int] = None


def parse_sse_lines(lines: Iterable[str]) -> Generator[SSEEvent, None, None]:
    """Parse a stream of lines into SSE events.

    This implementation is intentionally minimal but supports:
    - multi-line `data:` fields (joined with '\n')
    - `event:`, `id:`, `retry:` fields
    - comment/empty lines

    Yields SSEEvent for each event block.
    """

    data_lines: List[str] = []
    event: Optional[str] = None
    event_id: Optional[str] = None
    retry: Optional[int] = None

    def emit() -> Optional[SSEEvent]:
        nonlocal data_lines, event, event_id, retry
        if not data_lines and event is None and event_id is None and retry is None:
            return None
        payload = "\n".join(data_lines)
        out = SSEEvent(event=event, data=payload, id=event_id, retry=retry)
        data_lines = []
        event = None
        event_id = None
        retry = None
        return out

    for raw in lines:
        # strip CRLF
        line = raw.rstrip("\r\n")
        if line == "":
            maybe = emit()
            if maybe is not None:
                yield maybe
            continue
        if line.startswith(":"):
            # comment line
            continue

        field, sep, value = line.partition(":")
        if sep == "":
            # malformed line, ignore
            continue
        if value.startswith(" "):
            value = value[1:]

        if field == "data":
            data_lines.append(value)
        elif field == "event":
            event = value
        elif field == "id":
            event_id = value
        elif field == "retry":
            try:
                retry = int(value)
            except ValueError:
                retry = None

    maybe = emit()
    if maybe is not None:
        yield maybe
