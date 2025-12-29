import sys
import traceback

from ok import Logger
logger = Logger.get_logger(__name__)

from custom.ok_wrap import (
    start_ok_and_game,
    run_onetime_task,
    request_shutdown,
    read_live_stamina
)
from custom.waves_api import WavesDailyClient, read_api_daily_info
from custom.time_utils import now
from custom.gsheet_manager import GoogleSheetClient, RunResult, SheetRunConfig
from custom.email_sender import send_daily_run_report
from src.task.DailyTask import DailyTask


RUN_MODE = "daily"


def _api_success(resp: dict | None) -> bool:
    if not isinstance(resp, dict):
        return False
    if resp.get("success") is True:
        return True
    return resp.get("code") in (0, 200, 1511)


def apply_daily_config(sheet_config: SheetRunConfig, daily_task: DailyTask) -> None:
    daily_task.config["Which to Farm"] = daily_task.support_tasks[0]
    daily_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    daily_task.config["Auto Farm all Nightmare Nest"] = sheet_config.run_nightmare
    logger.info(
        f"MY-OK_WW: Loaded daily config: run_daily={sheet_config.run_daily}, "
        f"tacet #{sheet_config.tacet_serial}, nightmare={sheet_config.run_nightmare}"
    )


def run() -> tuple[RunResult, SheetRunConfig]:
    sheet_client = GoogleSheetClient()
    sheet_config = sheet_client.fetch_run_config()

    result = RunResult(
        task_type = RUN_MODE,
        started_at = now(),
        ended_at = None,
        status = "running",
        run_nightmare = sheet_config.run_nightmare
    )

    client = WavesDailyClient()
    try:
        try:
            sign_in_resp = client.sign_in()
            result.sign_in_success = _api_success(sign_in_resp)
        except Exception:
            result.sign_in_success = False
        stamina, backup_stamina, daily_points = read_api_daily_info(client=client)
    finally:
        client.close()

    result.stamina_start = stamina
    result.backup_stamina_start = backup_stamina
    result.stamina_left = stamina
    result.backup_stamina_left = backup_stamina
    result.stamina_used = 0
    result.daily_points = daily_points

    if not sheet_config.run_daily:
        result.ended_at = result.started_at
        result.status = "skipped"
        result.decision = "日常任务设置为不执行"
        result.run_nightmare = False
        
        sheet_client.update_stamina_from_run(result)
        sheet_client.append_run_result(result)
        send_daily_run_report(result, sheet_config)
        return result, sheet_config

    if daily_points is not None and daily_points >= 100:
        result.ended_at = result.started_at
        result.status = "skipped"
        result.decision = "日常任务已完成"
        result.run_nightmare = False

        sheet_client.update_stamina_from_run(result)
        sheet_client.append_run_result(result)
        send_daily_run_report(result, sheet_config)
        return result, sheet_config

    ok = None
    daily_task = None
    try:
        ok = start_ok_and_game()
        daily_task = ok.task_executor.get_task_by_class(DailyTask)
        apply_daily_config(sheet_config, daily_task)

        stamina, backup_stamina = read_live_stamina(daily_task)
        result.stamina_start = stamina
        result.backup_stamina_start = backup_stamina

        run_onetime_task(ok.task_executor, daily_task, timeout = 1200)

        result.daily_points = daily_task.info_get('total daily points', 0)
        if result.daily_points >= 100:
            result.status = "success"
        else:
            result.status = "needs review"

        stamina, backup_stamina = read_live_stamina(daily_task)
        result.stamina_left = stamina
        result.backup_stamina_left = backup_stamina
        result.fill_stamina_used()
        result.ended_at = now()
    except Exception as exc:
        result.status = "failure"
        result.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        logger.error("MY-OK-WW: Automation failed", exc)
    finally:
        if ok is not None:
            ok.task_executor.stop()
            if sheet_config.exit_game_after_daily or sheet_config.shutdown_after_daily:
                ok.device_manager.stop_hwnd()
            ok.quit()

    sheet_client.update_stamina_from_run(result)
    sheet_client.append_run_result(result)
    send_daily_run_report(result, sheet_config)
    
    return result, sheet_config


if __name__ == "__main__":
    result, sheet_config = run()
    exit_code = 0 if result.status != "failure" else 1
    if sheet_config.shutdown_after_daily:
        request_shutdown()
    sys.exit(exit_code)
