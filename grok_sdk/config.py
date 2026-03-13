from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import Optional

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_API_KEY = ""
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_BASE = 0.5
DEFAULT_RETRY_BACKOFF_MAX = 8.0


def _find_dotenv() -> Optional[Path]:
    """Find a .env file.

    Search order:
      1) GROK_DOTENV path (explicit override)
      2) Walk up from this file to find a directory containing pyproject.toml
         and use its .env
      3) Current working directory .env

    Returns None if not found.
    """
    override = os.getenv("GROK_DOTENV")
    if override:
        p = Path(override).expanduser()
        if p.exists() and p.is_file():
            return p

    # Try to locate project root by walking up from this package file.
    here = Path(__file__).resolve()
    for parent in [here.parent] + list(here.parents):
        if (parent / "pyproject.toml").exists():
            candidate = parent / ".env"
            if candidate.exists() and candidate.is_file():
                return candidate
            break

    cwd_candidate = Path.cwd() / ".env"
    if cwd_candidate.exists() and cwd_candidate.is_file():
        return cwd_candidate

    return None


def _load_dotenv() -> None:
    env_path = _find_dotenv()
    if env_path is None:
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class SDKConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    timeout: float = DEFAULT_TIMEOUT
    api_prefix: str = "/v1"
    verify_ssl: bool = True
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_backoff_base: float = DEFAULT_RETRY_BACKOFF_BASE
    retry_backoff_max: float = DEFAULT_RETRY_BACKOFF_MAX

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.retry_backoff_base < 0:
            raise ValueError("retry_backoff_base must be >= 0")
        if self.retry_backoff_max < 0:
            raise ValueError("retry_backoff_max must be >= 0")

    @classmethod
    def from_env(cls) -> "SDKConfig":
        _load_dotenv()
        base_url = os.getenv("GROK_BASE_URL", DEFAULT_BASE_URL)
        api_key = os.getenv("GROK_API_KEY", DEFAULT_API_KEY)
        timeout_raw = os.getenv("GROK_TIMEOUT")
        verify_ssl_raw = os.getenv("GROK_VERIFY_SSL")
        max_retries_raw = os.getenv("GROK_MAX_RETRIES")
        retry_backoff_base_raw = os.getenv("GROK_RETRY_BACKOFF_BASE")
        retry_backoff_max_raw = os.getenv("GROK_RETRY_BACKOFF_MAX")

        timeout = DEFAULT_TIMEOUT
        if timeout_raw:
            timeout = float(timeout_raw)

        verify_ssl = True
        if verify_ssl_raw is not None:
            verify_ssl = verify_ssl_raw.strip().lower() not in {"0", "false", "no"}

        max_retries = DEFAULT_MAX_RETRIES
        if max_retries_raw:
            max_retries = int(max_retries_raw)

        retry_backoff_base = DEFAULT_RETRY_BACKOFF_BASE
        if retry_backoff_base_raw:
            retry_backoff_base = float(retry_backoff_base_raw)

        retry_backoff_max = DEFAULT_RETRY_BACKOFF_MAX
        if retry_backoff_max_raw:
            retry_backoff_max = float(retry_backoff_max_raw)

        return cls(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            verify_ssl=verify_ssl,
            max_retries=max_retries,
            retry_backoff_base=retry_backoff_base,
            retry_backoff_max=retry_backoff_max,
        )

    def with_overrides(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        api_prefix: Optional[str] = None,
        verify_ssl: Optional[bool] = None,
        max_retries: Optional[int] = None,
        retry_backoff_base: Optional[float] = None,
        retry_backoff_max: Optional[float] = None,
    ) -> "SDKConfig":
        return replace(
            self,
            base_url=base_url if base_url is not None else self.base_url,
            api_key=api_key if api_key is not None else self.api_key,
            timeout=timeout if timeout is not None else self.timeout,
            api_prefix=api_prefix if api_prefix is not None else self.api_prefix,
            verify_ssl=verify_ssl if verify_ssl is not None else self.verify_ssl,
            max_retries=max_retries if max_retries is not None else self.max_retries,
            retry_backoff_base=(
                retry_backoff_base
                if retry_backoff_base is not None
                else self.retry_backoff_base
            ),
            retry_backoff_max=(
                retry_backoff_max
                if retry_backoff_max is not None
                else self.retry_backoff_max
            ),
        )

    def build_url(self, path: str) -> str:
        normalized_prefix = "/" + self.api_prefix.strip("/")
        normalized_path = "/" + path.lstrip("/")
        return f"{self.base_url.rstrip('/')}{normalized_prefix}{normalized_path}"
