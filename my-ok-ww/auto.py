from __future__ import annotations

import datetime as dt
import time
from typing import Iterable, Optional

from ok import OK, Logger, execute
from config import config as base_config

from src.task.BaseWWTask import BaseWWTask
from src.task.TacetTask import TacetTask

from manage_google_sheet import GoogleSheetClient, RunResult, SheetRunConfig
from mailgun_send import send_email


logger = Logger.get_logger(__name__)


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


def populate_result_from_infos(result: RunResult, info_sources: Iterable[dict]) -> None:
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
        f"体力任务: {'是' if sheet_config.run_stamina else '否'}",
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

    if not preferred.get("connected"):
        # Windows only; the configured calculate_pc_exe_path points to the fixed install.
        path = dm.get_exe_path(preferred)
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
    raise RuntimeError("Game window not ready within timeout.")


def fill_stamina_from_live(ok: OK | None, result: RunResult, stamina_task: TacetTask | None = None) -> None:
    """Try to read stamina directly if it was not recorded during task execution."""
    if ok is None:
        return
    if result.stamina_left is not None and result.backup_stamina is not None:
        return
    try:
        task = stamina_task or require_task(ok.task_executor, TacetTask)
        for _ in range(2):
            task.ensure_main(time_out=60, esc=True)
            # Open the book (F2) to show stamina and read it, then close.
            try:
                book_box = task.openF2Book("gray_book_boss")
                task.click_box(book_box, after_sleep=1)
                current, backup, _ = task.get_stamina()
                task.send_key('esc', after_sleep=1)
            except Exception:
                current, backup = -1, -1
            if current >= 0 and backup >= 0:
                result.stamina_left = current
                result.backup_stamina = backup
                return
            task.sleep(1)
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
