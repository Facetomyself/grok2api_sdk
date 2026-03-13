from pathlib import Path

from grok_sdk.config import SDKConfig


def test_find_dotenv_via_override(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("GROK_BASE_URL=http://example:8000\n", encoding="utf-8")
    monkeypatch.setenv("GROK_DOTENV", str(env))
    monkeypatch.delenv("GROK_BASE_URL", raising=False)

    cfg = SDKConfig.from_env()
    assert cfg.base_url == "http://example:8000"
