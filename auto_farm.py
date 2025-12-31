import traceback

from ok import Logger
logger = Logger.get_logger(__name__)

import time

from custom.ok_wrap import (
    start_ok,
    refresh_ok_until_ready,
    run_onetime_task,
    run_onetime_task_until_time,
    request_shutdown,
    read_echo_number
)
from custom.time_utils import now, format_duration, minutes_until_next_daily
from custom.gsheet_manager import GoogleSheetClient, FastFarmResult
from custom.task.my_FastFarmEchoTask import FastFarmEchoTask
from custom.task.my_FiveToOneTask import FiveToOneTask


STOP_HOUR = 1
STOP_MINUTE = 0

MERGE_MAX_RETRIES = 3


def calculate_farm_count(echo_number: int | None) -> int:
    if echo_number is None:
        return 100
    else:
        return round((3000 - echo_number) / 0.6)


def apply_farm_config(farm_target: int, farm_task: FastFarmEchoTask) -> None:
    farm_task.config["Repeat Farm Count"] = farm_target


def run():
    sheet_client = GoogleSheetClient()

    logger.info(f"MY-OK-WW: Selected run mode: farm")

    ok = start_ok()
    refresh_ok_until_ready(ok)
        
    farm_task = ok.task_executor.get_task_by_class(FastFarmEchoTask)
    merge_task = ok.task_executor.get_task_by_class(FiveToOneTask)

    seconds_to_run = minutes_until_next_daily(target_hour=STOP_HOUR, target_minute=STOP_MINUTE) * 60
    logger.info(f"MY-OK-WW: 运行时间 {format_duration(seconds_to_run)}")
    target_stop_time = time.time() + seconds_to_run

    while time.time() < target_stop_time:
        result = FastFarmResult(
                started_at = now(),
                ended_at = None,
                status = "running"
            )
        
        try:
            result.echo_number_start = read_echo_number(farm_task, retries=3)
            farm_target = calculate_farm_count(result.echo_number_start)
            apply_farm_config(farm_target, farm_task)
            logger.info(f"MY-OK-WW: 已设置进行 {farm_target} 次战斗")
            run_onetime_task_until_time(ok.task_executor, farm_task, hour=STOP_HOUR, minute=STOP_MINUTE)
            
            result.ended_at = now()
            result.fight_count = farm_task.info_get("Fight Count")

            logger.info(f"MY-OK-WW: 开始等待复活")
            time.sleep(300)
            
            result.echo_number_end = read_echo_number(farm_task, retries=3)

            total_merge_count = 0
            remaining_merge_count = None
            for attempt in range(1, MERGE_MAX_RETRIES + 1):
                run_onetime_task(ok.task_executor, merge_task)
                total_merge_count += merge_task.info_get("Merge Count") or 0
                remaining_merge_count = merge_task.info_get("Remaining Merge Count")
                if remaining_merge_count == 0:
                    break
                if attempt < MERGE_MAX_RETRIES:
                    logger.info(f"MY-OK-WW: Merge task exited early. Retrying {attempt + 1}/{MERGE_MAX_RETRIES}")
                    time.sleep(10)
            result.merge_count = total_merge_count
            result.status = "success"

            sheet_client.append_fast_farm_result(result)

        except Exception as exc:
            result.status = "failure"
            result.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            logger.error("MY-OK-WW: Automation failed", exc)

            sheet_client.append_fast_farm_result(result)
            
            break

    ok.device_manager.stop_hwnd()
    ok.quit()

if __name__ == "__main__":
    run()
    request_shutdown()
