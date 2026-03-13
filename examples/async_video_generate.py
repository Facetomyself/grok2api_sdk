import asyncio
import sys
from pathlib import Path


async def main() -> None:
    # Allow running examples without installing the package.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from grok_sdk import AsyncGrokSDKClient

    async with AsyncGrokSDKClient() as client:
        result = await client.videos.generate(
            model="grok-imagine-1.0-video",
            prompt="A futuristic train passing through floating mountains",
            request_timeout=180,
            video_length=5,
            aspect_ratio="3:2",
            resolution="SD",
            preset="normal",
        )
        print(result)
        print("assets:", client.videos.extract_assets(result))
        saved = await client.videos.download_assets(
            result, Path("outputs") / "videos_async"
        )
        print(
            "saved:",
            {
                "videos": [str(p) for p in saved["videos"]],
                "posters": [str(p) for p in saved["posters"]],
            },
        )


if __name__ == "__main__":
    asyncio.run(main())
