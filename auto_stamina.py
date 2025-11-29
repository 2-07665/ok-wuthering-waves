from __future__ import annotations

import datetime as dt
import traceback

from ok import Logger

from auto import (
    bootstrap_ok,
    fill_stamina_from_live,
    populate_result_from_infos,
    read_live_stamina,
    require_task,
    run_onetime_task,
    send_summary_email,
    stop_game,
    update_sheet_stamina,
)
from manage_google_sheet import GoogleSheetClient, RunResult, SheetRunConfig
from src.task.my_BootstrapMainTask import BootstrapMainTask
from src.task.TacetTask import TacetTask


logger = Logger.get_logger(__name__)
RUN_MODE = "stamina"
DAILY_TARGET_HOUR: int | None = 16  # set to your daily run hour
DAILY_TARGET_MINUTE: int | None = 0  # set to your daily run minute


def apply_stamina_config(sheet_config: SheetRunConfig, stamina_task: TacetTask, burn: int) -> None:
    stamina_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    stamina_task.config["Max Stamina to Spend"] = burn
    stamina_task.config["Prefer Single Spend"] = True
    stamina_task.config.save_file()
    logger.info(
        f"Loaded stamina config: tacet #{sheet_config.tacet_serial}, "
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


def minutes_until_next_daily(target_hour: int | None = None, target_minute: int | None = None) -> int:
    """Compute minutes until the next daily run target time (defaults to 24h later)."""
    now = dt.datetime.now()
    if target_hour is None or target_minute is None:
        return 24 * 60
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return int((target - now).total_seconds() // 60)


def calculate_burn(current: int | None, backup: int | None, minutes_to_next: int) -> tuple[bool, int, int | None, str]:
    """Return (should_run, burn_amount, projected_total, reason)."""
    if current is None or backup is None:
        return True, 60, None, "无法读取体力，按默认消耗一次"
    current = max(0, current)
    backup = max(0, backup)
    future_current, future_backup = predict_future_stamina(current, backup, minutes_to_next)
    future_total = future_current + future_backup
    if future_total <= 240:
        return False, 0, future_total, "预计不会溢出，无需体力任务"

    target_total = 180
    burn_needed = max(0, future_total - target_total)
    available = current + backup
    burn = min(available, burn_needed)
    burn = (burn // 60) * 60  # align to task spend units
    if burn < 60:
        return False, 0, future_total, "可消耗体力不足 60，跳过"
    return True, burn, future_total - burn, f"预计至下次日常有 {future_total} 体力，消耗至约 {target_total}"


def run() -> None:
    sheet_client = GoogleSheetClient()
    sheet_config = sheet_client.fetch_run_config()

    started_at = dt.datetime.now()
    logger.info(f"Selected run mode: {RUN_MODE}")

    result = RunResult(
        started_at=started_at,
        ended_at=None,
        task_type=RUN_MODE,
        status="running",
    )

    skip_reason = None
    if not sheet_config.run_stamina:
        skip_reason = "run_stamina set to False"

    if skip_reason:
        result.status = "skipped"
        result.error = skip_reason
        result.decision = skip_reason
        result.ended_at = started_at
        logger.info(f"Skipping run: {skip_reason}")
        sheet_client.append_run_result(result)
        send_summary_email(result, sheet_config, RUN_MODE)
        return

    ok = None
    stamina_task: TacetTask | None = None
    try:
        ok = bootstrap_ok()
        executor = ok.task_executor
        bootstrap_task = require_task(executor, BootstrapMainTask)
        run_onetime_task(executor, bootstrap_task, timeout=bootstrap_task.config.get("Main Timeout", 900))
        stamina_task = require_task(executor, TacetTask)
        stamina_task.info_clear()

        current, backup = read_live_stamina(ok, stamina_task)
        result.stamina_start = current
        result.backup_start = backup
        if current is not None and backup is not None:
            result.stamina_left = current
            result.backup_stamina = backup

        minutes_to_next = minutes_until_next_daily(DAILY_TARGET_HOUR, DAILY_TARGET_MINUTE)
        should_run, burn, projected_total, reason = calculate_burn(current, backup, minutes_to_next)
        result.projected_daily_stamina = projected_total
        result.decision = reason
        if should_run:
            apply_stamina_config(sheet_config, stamina_task, burn)

            run_onetime_task(executor, stamina_task, timeout=1800)

            result.status = "success"
            populate_result_from_infos(result, (stamina_task.info,))
            fill_stamina_from_live(ok, result, stamina_task=stamina_task)
        else:
            result.status = "skipped"
            result.error = reason
            logger.info(f"Skipping run: {reason}")
    except Exception as exc:  # noqa: BLE001
        result.status = "failed"
        result.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        logger.error("Automation failed", exc)
        fill_stamina_from_live(ok, result, stamina_task=stamina_task)
    finally:
        result.ended_at = dt.datetime.now()
        if ok is not None:
            ok.task_executor.stop()
            stop_game(ok)
            ok.quit()

    sheet_client.append_run_result(result)
    update_sheet_stamina(sheet_client, result)
    send_summary_email(result, sheet_config, RUN_MODE)


if __name__ == "__main__":
    run()
