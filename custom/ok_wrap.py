from config import config
from ok import OK, Logger, execute
logger = Logger.get_logger(__name__)
import custom.log_filter

from src.task.BaseWWTask import BaseWWTask
from src.task.DailyTask import DailyTask

import time
import re
from custom.time_utils import now, format_timestamp, minutes_until_next_daily

import subprocess

from custom.env_vars import env

def start_ok() -> OK:
    config["use_gui"] = False
    ok = OK(config)
    return ok


def ensure_ok_and_game_ready(ok: OK) -> None:
    dm = ok.device_manager
    dm.do_refresh(True)
    preferred = dm.get_preferred_device()

    if not preferred.get("connected"):
        game_exe_path = env("GAME_EXE_PATH", required=True)
        logger.info(f"MY-OK-WW: Launching game from {game_exe_path}")
        execute(game_exe_path)
        time.sleep(20)

    refresh_ok_until_ready(ok)


def refresh_ok(ok: OK) -> bool:
    dm = ok.device_manager
    dm.do_refresh(True)
    preferred = dm.get_preferred_device()
    capture_ready = (preferred and preferred.get("connected") and dm.capture_method is not None and dm.capture_method.connected())
    interaction_ready = dm.interaction is not None
    if capture_ready and interaction_ready:
        return True
    return False


def refresh_ok_until_ready(ok: OK, timeout: int = 120) -> None:
    start = time.time()
    while time.time() - start < timeout:
        if refresh_ok(ok):
            ok.task_executor.start()
            logger.info("MY-OK-WW: ok is ready")
            return
        time.sleep(5)
    raise RuntimeError("MY-OK-WW: ok not ready within timeout")


def auto_login(ok: OK, total_timeout: int = 300) -> None:
    logger.info("MY-OK-WW: Start auto login")
    task = ok.task_executor.get_task_by_class(DailyTask)

    if task.in_team_and_world():
        logger.info("MY-OK-WW: Already in main. No need to login")
        return

    def handle_update_restart():
        notice = task.wait_ocr(0.15, 0.25, to_x=0.85, to_y=0.75, match=[re.compile("更新完成"), re.compile("重启")], time_out=1, raise_if_not_found=False, settle_time=0.5)
        if notice is None:
            return
        logger.info("MY-OK-WW: Detected update completion prompt")
        confirm = task.wait_click_ocr(0.45, 0.55, to_x=0.80, to_y=0.78, match="确认", time_out=3, raise_if_not_found=False, settle_time=0.5)
        if confirm is None:
            logger.info("MY-OK-WW: Couldn't find confirm button, trying to stop the game")
            ok.device_manager.stop_hwnd()
            time.sleep(5)
            ensure_ok_and_game_ready(ok)
        else:
            logger.info("MY-OK-WW: Clicked restart button")
            time.sleep(20)
            refresh_ok_until_ready(ok)

    start = time.time()
    while time.time() - start < total_timeout:
        if task.wait_login():
            logger.info("MY-OK-WW: Login completed")
            return
        handle_update_restart()
        time.sleep(3)
    raise RuntimeError("MY-OK-WW: Auto login not finished within timeout")


def start_ok_and_game() -> OK:
    ok = start_ok()
    ensure_ok_and_game_ready(ok)
    auto_login(ok)
    return ok


def run_onetime_task(executor, task, *, timeout: int = 1800) -> None:
    task.enable()
    task.unpause()
    start = time.time()
    while time.time() - start < timeout:
        if executor.exit_event.is_set():
            raise RuntimeError("MY-OK-WW: Executor exit event set before task finished")
        if not task.enabled and executor.current_task is None:
            task.running = False
            return
        time.sleep(2)
    raise TimeoutError(f"MY-OK-WW: {task.name} did not finish within {timeout} seconds")


def run_onetime_task_until_time(executor, task, *, hour: int, minute: int = 0, poll_interval: int = 10) -> None:
    task.enable()
    task.unpause()

    deadline_ts = time.time() + minutes_until_next_daily(target_hour=hour, target_minute=minute) * 60

    while True:
        if executor.exit_event.is_set():
            raise RuntimeError("MY-OK-WW: Executor exit event set before task finished")
        if not task.enabled and executor.current_task is None:
            task.running = False
            return
        if time.time() >= deadline_ts:
            task.disable()
            task.unpause()
            logger.info(f"MY-OK-WW: 到达设定时间，Stopped {task.name} at {format_timestamp(now())}")
            return
        time.sleep(poll_interval)


def request_shutdown():
    """power off the machine via Windows shutdown."""
    subprocess.run(["shutdown.exe", "/s", "/t", "5"])


# region Read Data
def read_live_stamina(task: BaseWWTask) -> tuple[int | None, int | None]:
    """Open the stamina panel and return stamina."""
    try:
        task.ensure_main(esc=True, time_out=60)
        book_box = task.openF2Book("gray_book_boss")
        task.click_box(book_box, after_sleep=1)
        stamina, backup_stamina, _ = task.get_stamina()
        task.send_key("esc", after_sleep=1)
        if stamina < 0:
            return None, None
        return stamina, backup_stamina
    except Exception as exc:
        logger.error("MY-OK-WW: Failed to read live stamina", exc)
        return None, None


stamina_re = re.compile(r'^(\d+)/240$')
backup_stamina_re = re.compile(r'^(\d+)$')

def my_read_live_stamina(task: BaseWWTask) -> tuple[int | None, int | None]:
    """Open the stamina panel and return stamina."""
    try:
        task.ensure_main(esc=True, time_out=60)
        book_box = task.openF2Book("gray_book_boss")
        task.click_box(book_box, after_sleep=1)

        #stamina, backup_stamina, _ = task.get_stamina()
        #if stamina < 0:
        #    return None, None

        stamina_box = task.wait_ocr(0.756, 0.035, 0.830, 0.082, raise_if_not_found=False, match=stamina_re)
        backup_stamina_box = task.wait_ocr(0.636, 0.032, 0.711, 0.085, raise_if_not_found=False, match=backup_stamina_re)
        if stamina_box:
            stamina = int(stamina_box[0].name.split('/')[0])
        else:
            stamina = None
        if backup_stamina_box:
            backup_stamina = int(backup_stamina_box[0].name)
        else:
            backup_stamina = None
        logger.info(f"MY-OK-WW: 当前体力 {stamina}，当前后备体力 {backup_stamina}")

        task.send_key("esc", after_sleep=1)
        return stamina, backup_stamina
    except Exception as exc:
        logger.error("MY-OK-WW: Failed to read live stamina", exc)
        return None, None


def read_echo_number(task: BaseWWTask) -> int | None:
    try:
        task.ensure_main(esc=True, time_out=60)
        logger.info("MY-OK-WW: 打开背包")
        task.send_key_down("alt")
        task.sleep(0.05)
        task.click_relative(0.17, 0.045)
        task.send_key_up("alt")
        task.sleep(2)
        task.click_relative(0.04, 0.3)

        echo_number_box = task.wait_ocr(0.087, 0.035, 0.183, 0.091, match=re.compile(r'^(\d+)/3000$'), raise_if_not_found=False, time_out=5)

        if echo_number_box:
            echo_number = int(echo_number_box[0].name.split('/')[0])
            logger.info(f"MY-OK-WW: 当前拥有 {echo_number} 声骸")
        else:
            echo_number = None
            logger.error(f"MY-OK-WW: 读取声骸数量识别失败")
        return echo_number
    
    except Exception as exc:
        logger.error(f"MY-OK-WW: 读取声骸数量失败", exc)
        return None

# endregion
