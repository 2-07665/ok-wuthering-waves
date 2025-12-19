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
from custom.time_utils import now
from custom.gsheet_manager import GoogleSheetClient, RunResult, SheetRunConfig
from src.task.DailyTask import DailyTask


RUN_MODE = "daily"


def apply_daily_config(sheet_config: SheetRunConfig, daily_task: DailyTask) -> None:
    daily_task.config["Which to Farm"] = daily_task.support_tasks[0]
    daily_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    daily_task.config["Auto Farm all Nightmare Nest"] = sheet_config.run_nightmare
    daily_task.config.save_file()
    logger.info(
        f"MY-OK_WW: Loaded daily config: run_daily={sheet_config.run_daily}, "
        f"tacet #{sheet_config.tacet_serial}, nightmare={sheet_config.run_nightmare}"
    )


def run() -> tuple[RunResult, SheetRunConfig]:
    sheet_client = GoogleSheetClient()
    sheet_config = sheet_client.fetch_run_config()

    logger.info(f"MY-OK-WW: Selected run mode: {RUN_MODE}")

    result = RunResult(
        task_type = RUN_MODE,
        started_at = now(),
        ended_at = None,
        status = "running",
        run_nightmare = sheet_config.run_nightmare
    )

    if not sheet_config.run_daily:
        result.status = "skipped"
        result.decision = "日常任务设置为不执行"
        result.ended_at = now()
        result.run_nightmare = False
        logger.info(f"MY-OK-WW: Skipping run because {result.decision}")

        sheet_client.append_run_result(result)
        return result, sheet_config

    ok = None
    try:
        ok = start_ok_and_game()
        executor = ok.task_executor
        
        daily_task = executor.get_task_by_class(DailyTask)
        apply_daily_config(sheet_config, daily_task)
        stamina, backup_stamina = read_live_stamina(ok, daily_task)
        result.stamina_start = stamina
        result.backup_stamina_start = backup_stamina

        run_onetime_task(executor, daily_task, timeout = 1200)

        result.status = "success"
        result.daily_points = daily_task.info_get('total daily points')
        stamina, backup_stamina = read_live_stamina(ok, daily_task)
        result.stamina_left = stamina
        result.backup_stamina_left = backup_stamina
        result.fill_used_stamina()
    except Exception as exc:
        result.status = "failure"
        result.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        logger.error("MY-OK-WW: Automation failed", exc)
    finally:
        result.ended_at = now()
        if ok is not None:
            executor.stop()
            if sheet_config.exit_game_after_daily or sheet_config.shutdown_after_daily:
                ok.device_manager.stop_hwnd()
            ok.quit()

    sheet_client.update_stamina_from_run(result)
    sheet_client.append_run_result(result)
    
    return result, sheet_config


if __name__ == "__main__":
    result, sheet_config = run()
    exit_code = 0 if result.status != "failure" else 1
    if sheet_config.shutdown_after_daily:
        request_shutdown()
    sys.exit(exit_code)
