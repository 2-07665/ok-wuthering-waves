import sys
import traceback

from ok import Logger
logger = Logger.get_logger(__name__)

from custom.ok_wrap import (
    start_ok_and_game,
    run_onetime_task,
    request_shutdown,
    read_live_stamina,
)
from custom.waves_api import read_api_daily_info
from custom.time_utils import now, calculate_burn
from custom.gsheet_manager import GoogleSheetClient, RunResult, SheetRunConfig
from src.task.TacetTask import TacetTask


RUN_MODE = "stamina"


def apply_stamina_config(sheet_config: SheetRunConfig, stamina_task: TacetTask, burn: int) -> None:
    stamina_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    stamina_task.config["Max Stamina to Spend"] = burn
    stamina_task.config["Prefer Single Spend"] = True
    logger.info(
        f"MY-OK-WW: Loaded stamina config: run_stamina={sheet_config.run_stamina}, "
        f"tacet #{sheet_config.tacet_serial}, burn={burn}"
    )


def run() -> tuple[RunResult, SheetRunConfig]:
    sheet_client = GoogleSheetClient()
    sheet_config = sheet_client.fetch_run_config()

    result = RunResult(
        task_type = RUN_MODE,
        started_at = now(),
        ended_at = None,
        status = "running",
    )

    if not sheet_config.run_stamina:
        result.ended_at = result.started_at
        result.status = "skipped"
        result.decision = "体力任务设置为不执行"
        logger.info(f"MY-OK_WW: Skipping run because {result.decision}")
        sheet_client.append_run_result(result)
        return result, sheet_config

    ok = None
    stamina_task = None
    try:
        stamina, backup_stamina, _ = read_api_daily_info()

        if stamina is None:
            ok = start_ok_and_game()
            logger.warning("MY-OK-WW: API 体力读取失败，改为游戏内读取")
            stamina_task = ok.task_executor.get_task_by_class(TacetTask)
            stamina, backup_stamina = read_live_stamina(stamina_task)
        else:
            print(f"MY-OK-WW: API读取 体力 {stamina}，后备体力 {backup_stamina}\n")

        result.stamina_start = stamina
        result.backup_stamina_start = backup_stamina

        should_run, burn, condition, reason = calculate_burn(stamina, backup_stamina)
        result.decision = reason

        if should_run:
            if ok is None:
                ok = start_ok_and_game()
                stamina_task = ok.task_executor.get_task_by_class(TacetTask)

            apply_stamina_config(sheet_config, stamina_task, burn)
            run_onetime_task(ok.task_executor, stamina_task, timeout = 600)
            
            stamina, backup_stamina = read_live_stamina(stamina_task)

            result.stamina_left = stamina
            result.backup_stamina_left = backup_stamina
            result.fill_stamina_used()

            if condition and result.stamina_used == burn:
                result.status = "success"
            else:
                result.status = "needs review"
            result.ended_at = now()

        else:
            result.ended_at = result.started_at
            result.stamina_left = result.stamina_start
            result.backup_stamina_left = result.backup_stamina_start
            result.stamina_used = 0
            logger.info(f"MY-OK-WW: Skipping run because {reason}")

            if condition:
                result.status = "skipped"
            else:
                result.status = "needs review"
    except Exception as exc:
        result.status = "failure"
        result.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        logger.error("MY-OK-WW: Automation failed", exc)
    finally:
        if ok is not None:
            ok.task_executor.stop()
            if sheet_config.exit_game_after_stamina or sheet_config.shutdown_after_stamina:
                ok.device_manager.stop_hwnd()
            ok.quit()

    sheet_client.update_stamina_from_run(result)
    sheet_client.append_run_result(result)

    return result, sheet_config


if __name__ == "__main__":
    result, sheet_config = run()
    exit_code = 0 if result.status != "failure" else 1
    if sheet_config.shutdown_after_stamina:
        request_shutdown()
    sys.exit(exit_code)
