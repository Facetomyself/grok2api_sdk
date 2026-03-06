from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grok_sdk import GrokSDKClient


def main() -> None:
    with GrokSDKClient() as client:
        stream = client.chat.completions.stream(
            model="grok-3",
            messages=[{"role": "user", "content": "给我列 3 点 Python SDK 设计建议"}],
            temperature=0.4,
        )
        for event in stream:
            print(event)


if __name__ == "__main__":
    main()
