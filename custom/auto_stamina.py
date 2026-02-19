import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ok import Logger
logger = Logger.get_logger(__name__)

from custom.src.ok_wrap import (
    start_ok_and_game,
    run_onetime_task,
    request_shutdown,
    read_live_stamina,
)
from custom.src.waves_api import read_api_daily_info
from custom.src.time_utils import now, calculate_burn
from custom.src.env_vars import env_bool
from custom.src.gsheet_manager import GoogleSheetClient, RunResult, SheetRunConfig
from custom.src.email_sender import send_stamina_run_report

from custom.src.task.my_StaminaTask import StaminaTask


RUN_MODE = "stamina"

WAVES_API_ENABLED_ENV = "WAVES_API_ENABLED"
EMAIL_REPORT_ENABLED_ENV = "EMAIL_REPORT_ENABLED"


def which_to_farm_index(sheet_config: SheetRunConfig) -> int:
    which_to_farm_map: dict[str, int] = {
        "无音区": 0,
        "凝素领域": 1,
        "模拟领域": 2,
    }
    index = which_to_farm_map.get(sheet_config.which_to_farm.strip())
    if index is None:
        logger.warning(
            f"MY-OK-WW: Unknown which_to_farm='{sheet_config.which_to_farm}', defaulting to '无音区'"
        )
        index = 0
    return index

def apply_stamina_config(sheet_config: SheetRunConfig, task: StaminaTask) -> None:
    selected_idx = which_to_farm_index(sheet_config)

    task.config["Which to Farm"] = task.support_tasks[selected_idx]
    task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    task.config["Which Forgery Challenge to Farm"] = sheet_config.forgery_serial
    simulation_material_map: dict[str, str] = {
        "共鸣者经验": "Resonator EXP",
        "武器经验": "Weapon EXP",
        "贝币": "Shell Credit",
    }
    material = simulation_material_map.get(sheet_config.simulation_material.strip(), "Shell Credit")
    task.config["Material Selection"] = material

    logger.info(
        f"MY-OK_WW: Loaded stamina config: run_stamina={sheet_config.run_stamina}, "
        f"which_to_farm={sheet_config.which_to_farm}->{task.support_tasks[selected_idx]}, "
        f"tacet #{sheet_config.tacet_serial}, "
        f"forgery #{sheet_config.forgery_serial}, "
        f"material={material}. "
    )


def _send_stamina_report(result: RunResult, sheet_config: SheetRunConfig) -> None:
    if env_bool(EMAIL_REPORT_ENABLED_ENV, default=True):
        send_stamina_run_report(result, sheet_config)
        return
    logger.info(f"MY-OK-WW: Stamina email report disabled via {EMAIL_REPORT_ENABLED_ENV}")


def run() -> tuple[RunResult, SheetRunConfig]:
    sheet_client = GoogleSheetClient()
    sheet_config = sheet_client.fetch_run_config()

    result = RunResult(
        task_type = RUN_MODE,
        started_at = now(),
        ended_at = None,
        status = "running",
    )

    ok = None
    stamina_task = None
    try:
        stamina = backup_stamina = None
        if env_bool(WAVES_API_ENABLED_ENV, default=False):
            stamina, backup_stamina, _ = read_api_daily_info()

        if sheet_config.skip_stamina_once or (not sheet_config.run_stamina):
            result.ended_at = result.started_at
            result.status = "skipped"
            result.decision = "体力任务设置为不执行"

            result.fill_stamina_start(stamina, backup_stamina)
            result.fill_stamina_left_from_start()
            if result.stamina_start is not None:
                result.stamina_used = 0

            if sheet_config.skip_stamina_once:
                sheet_client.handle_skip_once(RUN_MODE)

            sheet_client.update_stamina_from_run(result)
            sheet_client.append_run_result(result)
            _send_stamina_report(result, sheet_config)
            return result, sheet_config

        if stamina is None:
            ok = start_ok_and_game()
            if env_bool(WAVES_API_ENABLED_ENV, default=False):
                logger.warning("MY-OK-WW: API 体力读取失败，改为游戏内读取")
            stamina_task = ok.task_executor.get_task_by_class(StaminaTask)
            stamina, backup_stamina = read_live_stamina(stamina_task)

        result.fill_stamina_start(stamina, backup_stamina)

        selected_idx = which_to_farm_index(sheet_config)
        burn_unit = 60 if selected_idx == 0 else 40

        should_run, burn, condition, reason = calculate_burn(stamina, backup_stamina, burn_unit)
        result.decision = reason

        if should_run:
            if ok is None or stamina_task is None:
                ok = start_ok_and_game()
                stamina_task = ok.task_executor.get_task_by_class(StaminaTask)
                stamina, backup_stamina = read_live_stamina(stamina_task)
            if stamina is not None:
                result.fill_stamina_start(stamina, backup_stamina)

            apply_stamina_config(sheet_config, stamina_task)
            run_onetime_task(ok.task_executor, stamina_task, timeout = 600)
            
            stamina, backup_stamina = read_live_stamina(stamina_task)

            result.fill_stamina_left(stamina, backup_stamina)
            result.fill_stamina_used()

            if condition and result.stamina_used == burn:
                result.status = "success"
            else:
                result.status = "needs review"
            result.ended_at = now()

        else:
            result.ended_at = result.started_at
            result.fill_stamina_left_from_start()
            if result.stamina_start is not None:
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
            if sheet_config.exit_game_after_stamina or sheet_config.shutdown_after_stamina:
                ok.device_manager.stop_hwnd()
            ok.quit()

    sheet_client.update_stamina_from_run(result)
    sheet_client.append_run_result(result)
    _send_stamina_report(result, sheet_config)
    return result, sheet_config


if __name__ == "__main__":
    result, sheet_config = run()
    exit_code = 0 if result.status != "failure" else 1
    if sheet_config.shutdown_after_stamina:
        request_shutdown()
    sys.exit(exit_code)
