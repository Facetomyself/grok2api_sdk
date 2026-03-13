from grok_sdk.config import SDKConfig
from grok_sdk.transport import HTTPTransport


def test_no_authorization_header_when_api_key_empty() -> None:
    cfg = SDKConfig(api_key="")
    transport = HTTPTransport(cfg)
    headers = transport._build_headers(None)
    assert "Authorization" not in headers
