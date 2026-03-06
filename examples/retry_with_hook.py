from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grok_sdk import GrokSDKClient, RequestLogEvent


def log_hook(event: RequestLogEvent) -> None:
    print(
        f"[{event.transport}] {event.phase} "
        f"{event.method} {event.path} "
        f"attempt={event.attempt}/{event.max_attempts} "
        f"status={event.status_code} "
        f"retry_delay={event.retry_delay_s} "
        f"duration_ms={event.duration_ms}"
    )


def main() -> None:
    with GrokSDKClient(
        max_retries=3,
        retry_backoff_base=0.5,
        retry_backoff_max=5.0,
        request_log_hook=log_hook,
    ) as client:
        print(client.models.list())


if __name__ == "__main__":
    main()
