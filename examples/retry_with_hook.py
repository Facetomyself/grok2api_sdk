import sys
from pathlib import Path


def log_hook(event) -> None:
    print(
        f"[{event.transport}] {event.phase} "
        f"{event.method} {event.path} "
        f"attempt={event.attempt}/{event.max_attempts} "
        f"status={event.status_code} "
        f"retry_delay={event.retry_delay_s} "
        f"duration_ms={event.duration_ms}"
    )


def main() -> None:
    # Allow running examples without installing the package.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from grok_sdk import GrokSDKClient

    with GrokSDKClient(
        max_retries=3,
        retry_backoff_base=0.5,
        retry_backoff_max=5.0,
        request_log_hook=log_hook,
    ) as client:
        print(client.models.list())


if __name__ == "__main__":
    main()
