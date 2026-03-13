import sys
from pathlib import Path


def main() -> None:
    # Allow running examples without installing the package.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from grok_sdk import APIError, GrokSDKClient

    image_path = Path("examples") / "tmp_test.png"
    if not image_path.exists():
        raise FileNotFoundError(
            "missing examples/tmp_test.png. "
            "prepare an image file first, then rerun this example."
        )

    with GrokSDKClient() as client:
        try:
            result = client.images.edit(
                model="grok-imagine-1.0-edit",
                prompt="Make this image watercolor style",
                images=[image_path],
                n=1,
                response_format="url",
            )
            print(result)
            saved = client.images.download_all(
                result, Path("outputs") / "edited_images"
            )
            print("saved:", [str(p) for p in saved])
        except APIError as exc:
            print("image edit failed:", exc)


if __name__ == "__main__":
    main()
