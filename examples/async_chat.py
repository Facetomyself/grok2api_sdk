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
        result = await client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": "请用一句话介绍异步 SDK 的价值"}],
            temperature=0.2,
        )
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
