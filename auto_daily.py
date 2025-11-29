from __future__ import annotations

import datetime as dt
import traceback

from ok import Logger

from auto import (
    bootstrap_ok,
    fill_stamina_from_live,
    populate_result_from_infos,
    require_task,
    run_onetime_task,
    send_summary_email,
    stop_game,
    update_sheet_stamina,
)
from manage_google_sheet import GoogleSheetClient, RunResult, SheetRunConfig
from src.task.my_BootstrapMainTask import BootstrapMainTask
from src.task.DailyTask import DailyTask


logger = Logger.get_logger(__name__)
RUN_MODE = "daily"


def apply_daily_config(sheet_config: SheetRunConfig, daily_task: DailyTask) -> None:
    daily_task.config["Which to Farm"] = daily_task.support_tasks[0]
    daily_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    daily_task.config["Auto Farm all Nightmare Nest"] = sheet_config.run_nightmare
    daily_task.config.save_file()
    logger.info(
        f"Loaded daily config: tacet #{sheet_config.tacet_serial}, "
        f"run_daily={sheet_config.run_daily}, nightmare={sheet_config.run_nightmare}"
    )


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
    if not sheet_config.run_daily:
        skip_reason = "run_daily set to False"

    if skip_reason:
        result.status = "skipped"
        result.error = skip_reason
        result.ended_at = started_at
        logger.info(f"Skipping run: {skip_reason}")
        sheet_client.append_run_result(result)
        send_summary_email(result, sheet_config, RUN_MODE)
        return

    ok = None
    try:
        ok = bootstrap_ok()
        executor = ok.task_executor
        bootstrap_task = require_task(executor, BootstrapMainTask)
        run_onetime_task(executor, bootstrap_task, timeout=bootstrap_task.config.get("Main Timeout", 900))
        daily_task = require_task(executor, DailyTask)
        apply_daily_config(sheet_config, daily_task)

        daily_task.info_clear()

        run_onetime_task(executor, daily_task, timeout=1800)

        result.status = "success"
        populate_result_from_infos(result, (daily_task.info,))
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
    send_summary_email(result, sheet_config, RUN_MODE)


if __name__ == "__main__":
    run()
