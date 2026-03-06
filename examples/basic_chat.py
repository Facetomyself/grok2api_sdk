from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grok_sdk import GrokSDKClient


def main() -> None:
    with GrokSDKClient() as client:
        result = client.chat.completions.create(
            model="grok-3",
            messages=[
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": "你好，帮我用一句话总结模块化 SDK 的价值"},
            ],
            temperature=0.3,
        )
        print(result)


if __name__ == "__main__":
    main()
