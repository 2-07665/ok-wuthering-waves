from __future__ import annotations

import datetime as dt
import sys
import traceback

from ok import Logger

from custom.auto import (
    bootstrap_ok,
    fill_stamina_from_live,
    read_live_stamina,
    run_onetime_task,
    send_summary_email,
    update_sheet_stamina,
)
from custom.manage_google_sheet import GoogleSheetClient, RunResult, SheetRunConfig
from custom.task.my_LoginTask import LoginTask
from src.task.TacetTask import TacetTask


logger = Logger.get_logger(__name__)
RUN_MODE = "stamina"
DAILY_TARGET_HOUR: int = 4
DAILY_TARGET_MINUTE: int = 30
SHUTDOWN_EXIT_CODE = 64  # bit flag added to exit code when shutdown is requested


def apply_stamina_config(sheet_config: SheetRunConfig, stamina_task: TacetTask, burn: int) -> None:
    stamina_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    stamina_task.config["Max Stamina to Spend"] = burn
    stamina_task.config["Prefer Single Spend"] = True
    stamina_task.config.save_file()
    logger.info(
        f"MY-OK-WW: Loaded stamina config: tacet #{sheet_config.tacet_serial}, "
        f"run_stamina={sheet_config.run_stamina}, burn={burn}"
    )


def predict_future_stamina(current: int, backup: int, minutes: int) -> tuple[int, int]:
    """Predict current/back-up stamina after `minutes` of regen."""
    current = min(current, 240)
    backup = min(backup, 480)
    gain_current = min(max(0, 240 - current), minutes // 6)
    current_after = current + gain_current
    remaining_minutes = max(0, minutes - gain_current * 6)
    gain_backup = min(max(0, 480 - backup), remaining_minutes // 12)
    backup_after = backup + gain_backup
    return current_after, backup_after


def minutes_until_next_daily(
    target_hour: int, target_minute: int, tz: dt.tzinfo | None = None
) -> int:
    """Compute minutes until the next target time in the given timezone (defaults to 24h later)."""
    tz = tz or dt.timezone(dt.timedelta(hours=8))
    now = dt.datetime.now(tz)
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return int((target - now).total_seconds() // 60)


def calculate_burn(current: int | None, backup: int | None, minutes_to_next: int) -> tuple[bool, int, int | None, str]:
    """Return (should_run, burn_amount, projected_total, reason)."""
    if current is None:
        return True, 60, None, "无法读取体力，按默认消耗一次"
    if backup is None:
        backup = 0
    current = max(0, current)
    backup = max(0, backup)
    future_current, future_backup = predict_future_stamina(current, backup, minutes_to_next)
    future_total = future_current + 2 * future_backup
    if future_total <= 240:
        return False, 0, future_total, f"预计下次日常有 {future_total} 体力，不会溢出"

    target_total = 190
    burn_needed = max(0, future_total - target_total)
    available = current + backup
    burn = min(available, burn_needed)
    burn = (burn // 60) * 60  # align to task spend units
    if burn < 60:
        return False, 0, future_total, f"预计下次日常有 {future_total} 体力，当前可消耗体力不足 60"
    return True, burn, future_total - burn, f"预计下次日常有 {future_total} 体力，消耗至 {future_total - burn}"


def run() -> tuple[RunResult, SheetRunConfig]:
    sheet_client = GoogleSheetClient()
    sheet_config = sheet_client.fetch_run_config()

    started_at = dt.datetime.now()
    logger.info(f"MY-OK-WW: Selected run mode: {RUN_MODE}")

    result = RunResult(
        started_at=started_at,
        ended_at=None,
        task_type=RUN_MODE,
        status="running",
    )

    skip_reason = None
    if not sheet_config.run_stamina:
        skip_reason = "体力任务设置为不执行"

    if skip_reason:
        result.status = "skipped"
        result.decision = skip_reason
        result.ended_at = started_at
        logger.info(f"MY-OK-WW: Skipping run because {skip_reason}")
        sheet_client.append_run_result(result)
        send_summary_email(result, sheet_config, RUN_MODE)
        return result, sheet_config

    ok = None
    stamina_task: TacetTask | None = None
    try:
        ok = bootstrap_ok()
        executor = ok.task_executor
        login_task = executor.get_task_by_class(LoginTask)
        run_onetime_task(
            executor,
            login_task,
            timeout=login_task.config.get("Login Timeout", login_task.executor.config.get("login_timeout", 600)),
        )
        stamina_task = executor.get_task_by_class(TacetTask)
        stamina_task.info_clear()

        current, backup = read_live_stamina(ok, stamina_task)
        result.stamina_start = current
        result.backup_start = backup if backup else 0

        minutes_to_next = minutes_until_next_daily(DAILY_TARGET_HOUR, DAILY_TARGET_MINUTE)
        should_run, burn, projected_total, reason = calculate_burn(current, backup, minutes_to_next)
        result.projected_daily_stamina = projected_total
        result.decision = reason
        if should_run:
            apply_stamina_config(sheet_config, stamina_task, burn)
            run_onetime_task(executor, stamina_task, timeout=600)

            result.status = "success"

            fill_stamina_from_live(ok, result, task=stamina_task)
            result.stamina_used = burn
        else:
            result.status = "skipped"
            result.stamina_used = 0
            logger.info(f"MY-OK-WW: Skipping run: {reason}")
    except Exception as exc:  # noqa: BLE001
        result.status = "failed"
        result.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        logger.error("MY-OK-WW: Automation failed", exc)
    finally:
        result.ended_at = dt.datetime.now()
        if ok is not None:
            ok.task_executor.stop()
            ok.device_manager.stop_hwnd()
            ok.quit()

    sheet_client.append_run_result(result)
    update_sheet_stamina(sheet_client, result)
    send_summary_email(result, sheet_config, RUN_MODE)
    return result, sheet_config


if __name__ == "__main__":
    result, sheet_config = run()
    exit_code = 0 if result.status != "failed" else 1
    if sheet_config.shutdown_after_stamina:
        exit_code |= SHUTDOWN_EXIT_CODE
    sys.exit(exit_code)
