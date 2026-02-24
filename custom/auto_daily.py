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
    read_live_stamina
)
from custom.src.waves_api import WavesDailyClient, read_api_daily_info, is_api_success
from custom.src.time_utils import now
from custom.src.env_vars import env_bool
from custom.src.gsheet_manager import GoogleSheetClient, RunResult, SheetRunConfig
from custom.src.notice import send_daily_run_report

from src.task.DailyTask import DailyTask


RUN_MODE = "daily"

WAVES_API_ENABLED_ENV = "WAVES_API_ENABLED"
NOTICE_ENABLED_ENV = "NOTICE_ENABLED"


def _send_daily_report(
    result: RunResult,
    sheet_config: SheetRunConfig,
    *,
    derived: RunResult.Derived | None = None,
) -> None:
    if env_bool(NOTICE_ENABLED_ENV, default=False):
        send_daily_run_report(result, sheet_config, derived=derived)
        return
    logger.info(f"MY-OK-WW: Daily task notice disabled via {NOTICE_ENABLED_ENV}")


def _persist_and_report(
    sheet_client: GoogleSheetClient,
    result: RunResult,
    sheet_config: SheetRunConfig,
) -> None:
    end_time = result.ensure_ended_at()
    derived = result.derive(end_time=end_time)
    sheet_client.update_stamina_from_run(result)
    sheet_client.append_run_result(result, derived=derived)
    _send_daily_report(result, sheet_config, derived=derived)


def apply_daily_config(sheet_config: SheetRunConfig, daily_task: DailyTask) -> None:
    which_to_farm_map: dict[str, int] = {
        "无音区": 0,
        "凝素领域": 1,
        "模拟领域": 2,
    }
    selected_idx = which_to_farm_map.get(sheet_config.which_to_farm.strip())
    if selected_idx is None:
        logger.warning(
            f"MY-OK-WW: Unknown which_to_farm='{sheet_config.which_to_farm}', defaulting to '无音区'"
        )
        selected_idx = 0

    daily_task.config["Which to Farm"] = daily_task.support_tasks[selected_idx]
    daily_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    daily_task.config["Which Forgery Challenge to Farm"] = sheet_config.forgery_serial

    simulation_material_map: dict[str, str] = {
        "共鸣者经验": "Resonator EXP",
        "武器经验": "Weapon EXP",
        "贝币": "Shell Credit",
    }
    material = simulation_material_map.get(sheet_config.simulation_material.strip(), "Shell Credit")
    daily_task.config["Material Selection"] = material
    daily_task.config["Auto Farm all Nightmare Nest"] = sheet_config.run_nightmare
    daily_task.config["Farm Nightmare Nest for Daily Echo"] = True
    logger.info(
        f"MY-OK_WW: Loaded daily config: run_daily={sheet_config.run_daily}, "
        f"which_to_farm={sheet_config.which_to_farm}->{daily_task.support_tasks[selected_idx]}, "
        f"tacet #{sheet_config.tacet_serial}, "
        f"forgery #{sheet_config.forgery_serial}, "
        f"material={material}, "
        f"nightmare={sheet_config.run_nightmare}"
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

    stamina = backup_stamina = daily_points = None
    if env_bool(WAVES_API_ENABLED_ENV, default=False):
        client = WavesDailyClient()
        sign_in_resp = client.sign_in()
        result.sign_in_success = is_api_success(sign_in_resp)
        stamina, backup_stamina, daily_points = read_api_daily_info(client=client)
        client.close()

    result.fill_stamina_start(stamina, backup_stamina)
    result.fill_stamina_left_from_start()
    result.daily_points = daily_points

    if sheet_config.skip_daily_once or (not sheet_config.run_daily):
        result.ended_at = result.started_at
        result.status = "skipped"
        result.decision = "日常任务设置为不执行"
        result.run_nightmare = False
        if result.stamina_start is not None:
            result.stamina_used = 0

        if sheet_config.skip_daily_once:
            sheet_client.handle_skip_once(RUN_MODE)

        _persist_and_report(sheet_client, result, sheet_config)
        return result, sheet_config

    if daily_points is not None and daily_points >= 100:
        result.ended_at = result.started_at
        result.status = "skipped"
        result.decision = "日常任务已完成"
        result.run_nightmare = False
        result.stamina_used = 0

        _persist_and_report(sheet_client, result, sheet_config)
        return result, sheet_config

    ok = None
    daily_task = None
    try:
        ok = start_ok_and_game()
        daily_task = ok.task_executor.get_task_by_class(DailyTask)
        apply_daily_config(sheet_config, daily_task)

        stamina, backup_stamina = read_live_stamina(daily_task)
        result.fill_stamina_start(stamina, backup_stamina)

        last_err = run_onetime_task(ok.task_executor, daily_task, timeout = 1800)
        result.error = last_err

        result.daily_points = daily_task.info_get("total daily points", 0)
        if result.daily_points is not None and result.daily_points >= 100:
            result.status = "success"
        else:
            result.status = "needs review"

        stamina, backup_stamina = read_live_stamina(daily_task)
        result.fill_stamina_left(stamina, backup_stamina)
        result.fill_stamina_used()
        result.ended_at = now()
    except Exception as exc:
        result.status = "failure"
        result.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        logger.error("MY-OK-WW: Automation failed", exc)
    finally:
        if ok is not None:
            if sheet_config.exit_game_after_daily or sheet_config.shutdown_after_daily:
                ok.device_manager.stop_hwnd()
            ok.quit()

    _persist_and_report(sheet_client, result, sheet_config)
    return result, sheet_config


if __name__ == "__main__":
    result, sheet_config = run()
    exit_code = 0 if result.status != "failure" else 1
    if sheet_config.shutdown_after_daily:
        request_shutdown()
    sys.exit(exit_code)
