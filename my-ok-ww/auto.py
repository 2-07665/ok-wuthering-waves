from __future__ import annotations

import argparse
import datetime as dt
import time
import traceback
from typing import Iterable, Optional

from ok import OK, Logger, execute
from config import config as base_config

from src.task.DailyTask import DailyTask
from src.task.TacetTask import TacetTask

from manage_google_sheet import GoogleSheetClient, RunResult, SheetRunConfig
from mailgun_send import send_email


logger = Logger.get_logger(__name__)

EXTRA_WINDOW_START = 2
EXTRA_WINDOW_END = 9

def run(mode: str = "auto"):
    sheet_client = GoogleSheetClient()
    sheet_config = sheet_client.fetch_run_config()
    run_mode = resolve_run_mode(mode, sheet_config)

    started_at = dt.datetime.now()
    logger.info(f"Selected run mode: {run_mode}")

    result = RunResult(
        started_at=started_at,
        ended_at=None,
        task_type=run_mode,
        status="running",
    )

    skip_reason = should_skip(run_mode, sheet_config)
    if skip_reason:
        result.status = "skipped"
        result.error = skip_reason
        result.ended_at = started_at
        logger.info(f"Skipping run: {skip_reason}")
        sheet_client.append_run_result(result)
        send_summary_email(result, sheet_config, run_mode)
        return

    ok = None
    try:
        ok = bootstrap_ok()
        executor = ok.task_executor
        daily_task = require_task(executor, DailyTask)
        tacet_task = require_task(executor, TacetTask)
        apply_sheet_config(sheet_config, daily_task, tacet_task)

        daily_task.info_clear()
        tacet_task.info_clear()

        if run_mode == "daily":
            run_onetime_task(executor, daily_task, timeout=1800)
        else:
            run_onetime_task(executor, tacet_task, timeout=1800)

        result.status = "success"
        populate_result_from_tasks(result, daily_task, tacet_task)
        fill_stamina_from_live(ok, result)
    except Exception as exc:  # noqa: BLE001
        result.status = "failed"
        result.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        logger.error("Automation failed", exc)
        fill_stamina_from_live(ok, result)
    finally:
        result.ended_at = dt.datetime.now()
        if ok is not None:
            ok.task_executor.stop()
            stop_game(ok)
            ok.quit()

    sheet_client.append_run_result(result)
    update_sheet_stamina(sheet_client, result)
    send_summary_email(result, sheet_config, run_mode)


def resolve_run_mode(mode: str, sheet_config: SheetRunConfig) -> str:
    """Resolve run mode based on CLI request and sheet configuration."""
    requested = mode.lower()
    if requested in {"daily", "stamina"}:
        return requested
    if requested != "auto":
        raise ValueError(f"Unknown mode: {mode}")

    now_hour = dt.datetime.now().hour
    if (
        sheet_config.run_extra_stamina
        and sheet_config.overflow_warning
        and EXTRA_WINDOW_START <= now_hour < EXTRA_WINDOW_END
    ):
        return "stamina"
    return "daily"


def should_skip(run_mode: str, sheet_config: SheetRunConfig) -> Optional[str]:
    if run_mode == "daily" and not sheet_config.run_daily:
        return "日常任务关闭，跳过运行"
    if run_mode == "stamina":
        if not sheet_config.run_extra_stamina:
            return "体力任务关闭，跳过运行"
        if not sheet_config.overflow_warning:
            return "体力不会溢出，无需体力任务"
    return None


def bootstrap_ok() -> OK:
    cfg = dict(base_config)
    cfg["use_gui"] = False
    ok = OK(cfg)
    ensure_game_running(ok, timeout=cfg.get("start_timeout", 120))
    return ok


def require_task(executor, cls):
    task = executor.get_task_by_class(cls)
    if task is None:
        raise RuntimeError(f"{cls.__name__} not available; check onetime_tasks in config.py")
    return task


def apply_sheet_config(sheet_config: SheetRunConfig, daily_task: DailyTask, tacet_task: TacetTask) -> None:
    daily_task.config["Which to Farm"] = daily_task.support_tasks[0]
    daily_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    daily_task.config["Auto Farm all Nightmare Nest"] = sheet_config.run_nightmare
    daily_task.config.save_file()

    tacet_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    tacet_task.config.save_file()
    logger.info(
        f"Loaded config from sheet: daily={sheet_config.run_daily}, tacet #{sheet_config.tacet_serial}, "
        f"nightmare={sheet_config.run_nightmare}, extra={sheet_config.run_extra_stamina}, "
        f"overflow={sheet_config.overflow_warning}"
    )


def run_onetime_task(executor, task, *, timeout: int = 1800) -> None:
    task.enable()
    task.unpause()
    start = time.time()
    while time.time() - start < timeout:
        if executor.exit_event.is_set():
            raise RuntimeError("Executor exit event set before task finished.")
        if not task.enabled and executor.current_task is None:
            if err := task.info.get("Error"):
                raise RuntimeError(err)
            task.running = False
            return
        time.sleep(1)
    raise TimeoutError(f"{task.name} did not finish within {timeout} seconds.")


def populate_result_from_tasks(result: RunResult, daily_task: DailyTask, tacet_task: TacetTask) -> None:
    info_sources: Iterable[dict] = (daily_task.info, tacet_task.info)
    result.daily_points = _first_int(info_sources, ["daily points", "total daily points"])
    result.stamina_used = _sum_int(info_sources, "used stamina")
    result.stamina_left = _first_int(info_sources, ["current_stamina"])
    result.backup_stamina = _first_int(info_sources, ["back_up_stamina"])


def _first_int(infos: Iterable[dict], keys: list[str]) -> Optional[int]:
    for info in infos:
        for key in keys:
            if key in info:
                try:
                    return int(info[key])
                except (TypeError, ValueError):
                    return None
    return None


def _sum_int(infos: Iterable[dict], key: str) -> Optional[int]:
    total = 0
    found = False
    for info in infos:
        if key in info:
            try:
                total += int(info[key])
                found = True
            except (TypeError, ValueError):
                return None
    return total if found else None

def send_summary_email(result: RunResult, sheet_config: SheetRunConfig, run_mode: str) -> None:
    subject_task = "日常任务" if run_mode == "daily" else "体力任务"
    subject_status_map = {
        "success": "成功",
        "failed": "失败",
        "skipped": "跳过",
    }
    subject_status = subject_status_map.get(result.status, result.status)
    subject = f"{result.started_at.date()} WW{subject_task}: {subject_status}"

    def fmt(val):
        return "未知" if val is None else val

    config_lines = [
        f"运行类型: {subject_task}",
        f"无音区序号: {sheet_config.tacet_serial}",
        f"梦魇巢穴: {'是' if sheet_config.run_nightmare else '否'}",
        f"体力任务: {'是' if sheet_config.run_extra_stamina else '否'}",
        f"体力溢出预警: {'是' if sheet_config.overflow_warning else '否'}",
    ]

    result_lines = [
        f"状态: {result.status}",
        f"体力消耗: {0 if result.stamina_used is None else result.stamina_used}",
        f"当前体力: {fmt(result.stamina_left)} / 备用 {fmt(result.backup_stamina)}",
    ]

    if run_mode == "daily":
        result_lines.append(f"日常积分: {fmt(result.daily_points)}")
        completed_daily = "未知"
        if result.daily_points is not None:
            completed_daily = (result.daily_points or 0) >= 100
        result_lines.append(f"是否完成日常任务: {'是' if completed_daily else '否'}")

    if result.error:
        result_lines.append(f"错误: {result.error}")

    body = "\n\n".join(["\n".join(config_lines), "\n".join(result_lines)])
    try:
        send_email(subject, body)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send summary email", exc)


def update_sheet_stamina(sheet_client: GoogleSheetClient, result: RunResult) -> None:
    """Push stamina numbers back to the Config sheet."""
    if result.stamina_left is None or result.backup_stamina is None:
        logger.warning("Stamina values missing; skipping sheet stamina update.")
        return
    try:
        sheet_client.update_stamina(result.stamina_left, result.backup_stamina, result.ended_at or dt.datetime.now())
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to update stamina on sheet", exc)


def ensure_game_running(ok: OK, timeout: int = 120) -> None:
    """Start the game if needed and wait until capture/interaction are ready."""
    dm = ok.device_manager
    dm.do_refresh(True)
    preferred = dm.get_preferred_device()
    if preferred is None:
        raise RuntimeError("No preferred device found; please start the game once or configure the device.")

    if preferred.get("device") == "windows" and not preferred.get("connected"):
        path = dm.get_exe_path(preferred)
        if not path:
            raise RuntimeError("Game path not detected; start the game manually once to record its path.")
        logger.info(f"Launching game from {path}")
        execute(path)

    end_time = time.time() + timeout
    while time.time() < end_time:
        dm.do_refresh(True)
        preferred = dm.get_preferred_device()
        capture_ready = (
            preferred
            and preferred.get("connected")
            and dm.capture_method is not None
            and dm.capture_method.connected()
        )
        interaction_ready = dm.interaction is not None
        if capture_ready and interaction_ready:
            return
        time.sleep(2)
    raise RuntimeError("Game window not ready within timeout; please open the game and try again.")


def fill_stamina_from_live(ok: OK | None, result: RunResult) -> None:
    """Try to read stamina directly if it was not recorded during task execution."""
    if ok is None:
        return
    if result.stamina_left is not None and result.backup_stamina is not None:
        return
    try:
        tacet_task = require_task(ok.task_executor, TacetTask)
        for _ in range(2):
            tacet_task.ensure_main(time_out=60, esc=True)
            # Open the book (F2) to show stamina and read it, then close.
            try:
                book_box = tacet_task.openF2Book("gray_book_boss")
                tacet_task.click_box(book_box, after_sleep=1)
                current, backup, _ = tacet_task.get_stamina()
                tacet_task.send_key('esc', after_sleep=1)
            except Exception:
                current, backup = -1, -1
            if current >= 0 and backup >= 0:
                result.stamina_left = current
                result.backup_stamina = backup
                return
            tacet_task.sleep(1)
        logger.warning("Failed to capture stamina after task; values remain unknown.")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to read live stamina", exc)


def stop_game(ok: OK) -> None:
    """Terminate the game process once all tasks are finished."""
    try:
        if ok.device_manager:
            ok.device_manager.stop_hwnd()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to stop game process", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Wuthering Waves automation headlessly.")
    parser.add_argument(
        "--mode",
        choices=["auto", "daily", "stamina"],
        default="auto",
        help="Select which workflow to run. auto=choose by time/overflow.",
    )
    args = parser.parse_args()
    run(args.mode)
