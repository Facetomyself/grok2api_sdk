from __future__ import annotations

from typing import Optional

from .config import SDKConfig
from .hooks import AsyncRequestLogHook
from .resources import (
    AsyncChatAPI,
    AsyncImagesAPI,
    AsyncModelsAPI,
    AsyncOpenAIVideosAPI,
    AsyncResponsesAPI,
    AsyncVideosAPI,
)
from .transport import AsyncHTTPTransport


class AsyncGrokSDKClient:
    def __init__(
        self,
        config: Optional[SDKConfig] = None,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        api_prefix: Optional[str] = None,
        verify_ssl: Optional[bool] = None,
        max_retries: Optional[int] = None,
        retry_backoff_base: Optional[float] = None,
        retry_backoff_max: Optional[float] = None,
        request_log_hook: Optional[AsyncRequestLogHook] = None,
    ) -> None:
        resolved_config = config or SDKConfig.from_env()
        if any(
            value is not None
            for value in [
                base_url,
                api_key,
                timeout,
                api_prefix,
                verify_ssl,
                max_retries,
                retry_backoff_base,
                retry_backoff_max,
            ]
        ):
            resolved_config = resolved_config.with_overrides(
                base_url=base_url,
                api_key=api_key,
                timeout=timeout,
                api_prefix=api_prefix,
                verify_ssl=verify_ssl,
                max_retries=max_retries,
                retry_backoff_base=retry_backoff_base,
                retry_backoff_max=retry_backoff_max,
            )

        self.config = resolved_config
        self._transport = AsyncHTTPTransport(
            self.config,
            request_log_hook=request_log_hook,
        )
        self.chat = AsyncChatAPI(self._transport)
        self.responses = AsyncResponsesAPI(self._transport)
        self.images = AsyncImagesAPI(self._transport)
        self.models = AsyncModelsAPI(self._transport)
        self.videos = AsyncVideosAPI(self._transport)
        self.openai_videos = AsyncOpenAIVideosAPI(self._transport)

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> "AsyncGrokSDKClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
