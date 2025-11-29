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
from src.task.TacetTask import TacetTask


logger = Logger.get_logger(__name__)
RUN_MODE = "stamina"


def apply_stamina_config(sheet_config: SheetRunConfig, stamina_task: TacetTask) -> None:
    stamina_task.config["Which Tacet Suppression to Farm"] = sheet_config.tacet_serial
    stamina_task.config.save_file()
    logger.info(
        f"Loaded stamina config: tacet #{sheet_config.tacet_serial}, "
        f"run_stamina={sheet_config.run_stamina}, overflow={sheet_config.overflow_warning}"
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
    if not sheet_config.run_stamina:
        skip_reason = "run_stamina set to False"
    elif not sheet_config.overflow_warning:
        skip_reason = "体力不会溢出，无需体力任务"

    if skip_reason:
        result.status = "skipped"
        result.error = skip_reason
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
        apply_stamina_config(sheet_config, stamina_task)

        stamina_task.info_clear()

        run_onetime_task(executor, stamina_task, timeout=1800)

        result.status = "success"
        populate_result_from_infos(result, (stamina_task.info,))
        fill_stamina_from_live(ok, result, stamina_task=stamina_task)
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
