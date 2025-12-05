from __future__ import annotations

import datetime as dt
import time
from typing import Iterable, Optional

from ok import OK, Logger, execute
from config import config as base_config

from src.task.BaseWWTask import BaseWWTask

from custom.manage_google_sheet import GoogleSheetClient, RunResult, SheetRunConfig
from custom.mailgun_send import (
    MAILGUN_TEMPLATE_DAILY,
    MAILGUN_TEMPLATE_STAMINA,
    send_email,
)


logger = Logger.get_logger(__name__)
STATUS_STYLES = {
    "success": ("成功", "#22c55e"),
    "failed": ("失败", "#ef4444"),
    "skipped": ("跳过", "#94a3b8"),
    "running": ("运行中", "#38bdf8"),
}


def bootstrap_ok() -> OK:
    cfg = dict(base_config)
    cfg["use_gui"] = False
    ok = OK(cfg)
    ensure_game_running(ok)
    return ok


def ensure_game_running(ok: OK, timeout: int = 120) -> None:
    """Start the game if needed and wait until capture/interaction are ready."""
    dm = ok.device_manager
    dm.do_refresh(True)
    preferred = dm.get_preferred_device()

    if not preferred.get("connected"):
        path = dm.get_exe_path(preferred)
        logger.info(f"MY-OK-WW: Launching game from {path}")
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
        time.sleep(3)
    raise RuntimeError("MY-OK-WW: Game window not ready within timeout.")


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


def backfill_stamina_used_from_totals(result: RunResult) -> None:
    """Derive stamina_used from start/end totals when it was not recorded."""
    if (
        result.stamina_used is not None
        or None in (result.stamina_start, result.backup_start, result.stamina_left, result.backup_stamina)
    ):
        return
    start_total = (result.stamina_start or 0) + (result.backup_start or 0)
    end_total = (result.stamina_left or 0) + (result.backup_stamina or 0)
    consumed = max(0, start_total - end_total)
    result.stamina_used = int(round(consumed / 60.0)) * 60


def send_summary_email(result: RunResult, sheet_config: SheetRunConfig, run_mode: str) -> None:
    subject_task = "日常任务" if run_mode == "daily" else "体力任务"
    status_label, status_color = STATUS_STYLES.get(result.status, (result.status, "#94a3b8"))
    subject = f"{result.started_at.date()} WW{subject_task}: {status_label}"

    start_ts = _format_timestamp(result.started_at)
    end_ts = _format_timestamp(result.ended_at or dt.datetime.now())
    duration = _format_duration_seconds(result.started_at, result.ended_at)
    daily_complete = result.daily_points is not None and (result.daily_points or 0) >= 100
    decision_note = result.decision or ("体力任务关闭" if result.status == "skipped" else "")

    def fmt(val: Optional[int]) -> str:
        return "未知" if val is None else str(val)

    tacet_desc = sheet_config.tacet_name or "未设置"
    set_desc = " / ".join(filter(None, [sheet_config.tacet_set1, sheet_config.tacet_set2])) or "未设置"
    projected = fmt(result.projected_daily_stamina)
    decision_text = decision_note or ""
    error_text = result.error or ""
    notes_display = "block" if (decision_text or error_text) else "none"
    template_path = MAILGUN_TEMPLATE_STAMINA if run_mode == "stamina" else MAILGUN_TEMPLATE_DAILY
    variables = {
        "title": f"{subject_task} · {status_label}",
        "run_mode_name": subject_task,
        "status_label": status_label,
        "status_color": status_color,
        "started_at": start_ts,
        "ended_at": end_ts,
        "duration": duration,
        "stamina_start": fmt(result.stamina_start),
        "backup_start": fmt(result.backup_start),
        "stamina_used": fmt(result.stamina_used),
        "stamina_left": fmt(result.stamina_left),
        "backup_stamina": fmt(result.backup_stamina),
        "decision": decision_text,
        "daily_points": fmt(result.daily_points),
        "daily_complete_label": "是" if daily_complete else "否",
        "tacet_name": tacet_desc,
        "tacet_set1": sheet_config.tacet_set1 or "未设置",
        "tacet_set2": sheet_config.tacet_set2 or "未设置",
        "error": error_text,
        "projected_daily_stamina": projected,
        "notes_display": notes_display,
        "decision_display": "block" if decision_text else "none",
        "error_display": "block" if error_text else "none",
    }
    if run_mode == "daily":
        variables["run_daily"] = "是" if sheet_config.run_daily else "否"
        variables["run_nightmare"] = "是" if sheet_config.run_nightmare else "否"
    else:
        variables["run_stamina"] = "是" if sheet_config.run_stamina else "否"

    text_lines = [
        f"运行类型: {subject_task}",
        f"状态: {status_label}",
        f"开始/结束: {start_ts} - {end_ts} ({duration})",
        f"体力: 开始 {fmt(result.stamina_start)} / {fmt(result.backup_start)}; 消耗 {fmt(result.stamina_used)} / 结束 {fmt(result.stamina_left)} / 备用 {fmt(result.backup_stamina)}",
        f"预计日常体力: {projected}",
        f"无音区: {tacet_desc}; 套装: {set_desc}; 梦魇巢穴: {'是' if sheet_config.run_nightmare else '否'}",
        f"决策: {decision_note or '无'}",
    ]
    if run_mode == "daily":
        text_lines.append(f"日常积分: {fmt(result.daily_points)} (是否完成: {'是' if daily_complete else '否'})")
    if result.error:
        text_lines.append(f"错误: {result.error}")
    body = "\n".join(text_lines)
    try:
        send_email(subject, body, variables=variables, template_path=template_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send summary email", exc)


def update_sheet_stamina(sheet_client: GoogleSheetClient, result: RunResult) -> None:
    """Push stamina numbers back to the Config sheet."""
    if result.stamina_left is None or result.backup_stamina is None:
        logger.warning("MY-OK-WW: Stamina values missing; skipping sheet stamina update.")
        return
    try:
        sheet_client.update_stamina(result.stamina_left, result.backup_stamina, result.ended_at or dt.datetime.now())
    except Exception as exc:  # noqa: BLE001
        logger.error("MY-OK-WW: Failed to update stamina on sheet", exc)


def fill_stamina_from_live(ok: OK | None, result: RunResult, task: BaseWWTask | None = None) -> None:
    """Try to read stamina directly if it was not recorded during task execution."""
    if ok is None:
        return
    if result.stamina_left is not None and result.backup_stamina is not None:
        return
    current, backup = read_live_stamina(ok, task)
    if current is not None and backup is not None:
        result.stamina_left = current
        result.backup_stamina = backup
        return
    logger.warning("Failed to capture stamina after task; values remain unknown.")


def read_live_stamina(ok: OK, task: BaseWWTask) -> tuple[int | None, int | None]:
    """Open the stamina panel and return current/back-up stamina."""
    try:
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
                return current, backup
            task.sleep(1)
        return None, None
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to read live stamina", exc)
        return None, None


def _format_timestamp(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_duration_seconds(start: dt.datetime, end: dt.datetime | None) -> str:
    end = end or dt.datetime.now()
    total_seconds = max(0, int(round((end - start).total_seconds())))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)
