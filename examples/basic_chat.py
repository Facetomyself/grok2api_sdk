import sys
from pathlib import Path


def main() -> None:
    # Allow running examples without installing the package.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from grok_sdk import GrokSDKClient

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
