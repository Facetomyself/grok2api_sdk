import sys
from pathlib import Path


def main() -> None:
    # Allow running examples without installing the package.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from grok_sdk import GrokSDKClient

    with GrokSDKClient() as client:
        print("image method:", client.images.method())
        result = client.images.generate(
            model="grok-imagine-1.0",
            prompt="A cyberpunk city at sunrise, cinematic style",
            n=1,
            response_format="url",
        )
        print(result)
        saved = client.images.download_all(result, Path("outputs") / "images")
        print("saved:", [str(p) for p in saved])


if __name__ == "__main__":
    main()
