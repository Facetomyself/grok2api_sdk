from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grok_sdk import GrokSDKClient


def main() -> None:
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
