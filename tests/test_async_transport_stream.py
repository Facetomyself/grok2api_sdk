import json

import httpx
import pytest

from grok_sdk.config import SDKConfig
from grok_sdk.transport import AsyncHTTPTransport


@pytest.mark.asyncio
async def test_async_stream_parses_sse_event_blocks() -> None:
    payload = {"x": 1}
    body = (
        "event: message\n"
        f"data: {json.dumps(payload)}\n"
        "\n"
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=body,
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    cfg = SDKConfig(base_url="http://test", api_key="")
    sdk_transport = AsyncHTTPTransport(cfg, client=client)

    out = []
    async for chunk in sdk_transport.stream(
        "/chat/completions",
        json_body={"model": "grok-3", "messages": [], "stream": True},
    ):
        out.append(chunk)

    assert out == [payload]
    await sdk_transport.close()
