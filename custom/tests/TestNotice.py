import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from custom.src.gsheet_manager import GoogleSheetClient, RunResult, SheetRunConfig
from custom.src.notice import send_daily_run_report, send_stamina_run_report
from custom.src.time_utils import now


def _sheet_config() -> SheetRunConfig:
    client = GoogleSheetClient()
    return client.fetch_run_config()


def _sample_daily_result() -> RunResult:
    start = now()
    end = start
    return RunResult(
        task_type="daily",
        started_at=start,
        ended_at=end,
        status="success",
        stamina_start=240,
        backup_stamina_start=100,
        stamina_used=240,
        stamina_left=0,
        backup_stamina_left=100,
        run_nightmare=True,
        daily_points=100,
        sign_in_success=True,
        decision="这是手动测试通知，请忽略。",
        error="",
    )


def _sample_stamina_result() -> RunResult:
    start = now()
    end = start
    return RunResult(
        task_type="stamina",
        started_at=start,
        ended_at=end,
        status="success",
        stamina_start=240,
        backup_stamina_start=100,
        stamina_used=240,
        stamina_left=0,
        backup_stamina_left=100,
        decision="这是手动测试通知，请忽略。",
        error="",
    )


def send_daily() -> bool:
    result = _sample_daily_result()
    cfg = _sheet_config()
    derived = result.derive(end_time=result.ensure_ended_at())
    ok = send_daily_run_report(result, cfg, derived=derived)
    print(f"Daily notice sent: {ok}")
    return ok


def send_stamina() -> bool:
    result = _sample_stamina_result()
    cfg = _sheet_config()
    derived = result.derive(end_time=result.ensure_ended_at())
    ok = send_stamina_run_report(result, cfg, derived=derived)
    print(f"Stamina notice sent: {ok}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send manual notice test messages using current custom/env configuration."
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "stamina", "both"],
        default="both",
        help="Which notice to send.",
    )
    args = parser.parse_args()

    if args.mode == "daily":
        return 0 if send_daily() else 1
    if args.mode == "stamina":
        return 0 if send_stamina() else 1

    ok_daily = send_daily()
    ok_stamina = send_stamina()
    return 0 if (ok_daily and ok_stamina) else 1


if __name__ == "__main__":
    raise SystemExit(main())
