from __future__ import annotations

import sys

from manage_google_sheet import GoogleSheetClient

SHUTDOWN_EXIT_CODE = 64


def main() -> None:
    client = GoogleSheetClient()
    config = client.fetch_run_config()
    shutdown_after_daily = bool(getattr(config, "shutdown_after_daily", False))
    print(f"shutdown_after_daily={shutdown_after_daily}")
    exit_code = SHUTDOWN_EXIT_CODE if shutdown_after_daily else 0
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
