import sys
from pathlib import Path


def main() -> None:
    # Allow running examples without installing the package.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from grok_sdk import GrokSDKClient

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
