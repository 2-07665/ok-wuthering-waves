import importlib
import re
import subprocess
import time

from config import config
from ok import OK, Logger, og
from ok.util.process import execute
from src.task.BaseWWTask import BaseWWTask
from src.task.DailyTask import DailyTask
from PySide6.QtCore import QCoreApplication

from . import log_filter
from .env_vars import env
from .patches import apply_all_patches
from .time_utils import format_timestamp, minutes_until_target_time, now
from .ui_boxes import get_ui_box

logger = Logger.get_logger(__name__)

def start_ok() -> OK:
    apply_all_patches()
    config["use_gui"] = False
    ok = OK(config)
    initialize_my_app(ok)
    return ok


def initialize_my_app(ok: OK) -> None:
    if og.my_app is not None:
        return
    my_app = config.get("my_app")
    if my_app is not None:
        module_name = my_app[0]
        class_name = my_app[1]
        module = importlib.import_module(module_name)
        my_app_cls = getattr(module, class_name)
        og.my_app = my_app_cls(ok.exit_event)
        logger.info("MY-OK-WW: Initialized og.my_app for non-GUI startup")


def ensure_ok_and_game_ready(ok: OK) -> None:
    dm = ok.device_manager
    dm.do_refresh(True)
    preferred = dm.get_preferred_device()

    if not preferred.get("connected"):
        game_exe_path = env("GAME_EXE_PATH", required=True)
        logger.info(f"MY-OK-WW: Launching game from {game_exe_path}")
        execute(game_exe_path)
        time.sleep(120)

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
        notice = task.wait_ocr(
            box=task.box_of_screen(*get_ui_box("登录界面更新提醒")),
            match=[re.compile("更新完成"), re.compile("重启")],
            time_out=1,
            raise_if_not_found=False,
            settle_time=0.5,
        )
        if notice is None:
            return
        logger.info("MY-OK-WW: Detected update completion prompt")
        confirm = task.wait_click_ocr(
            box=task.box_of_screen(*get_ui_box("登录界面更新提醒确认按钮")),
            match="确认",
            time_out=3,
            raise_if_not_found=False,
            settle_time=0.5,
        )
        if confirm is None:
            logger.info("MY-OK-WW: Couldn't find confirm button, trying to stop the game")
            ok.device_manager.stop_hwnd()
            time.sleep(5)
            ensure_ok_and_game_ready(ok)
        else:
            logger.info("MY-OK-WW: Clicked restart button")
            time.sleep(60)
            refresh_ok_until_ready(ok)

    start = time.time()
    while time.time() - start < total_timeout:
        if task.wait_login():
            logger.info("MY-OK-WW: Login completed")
            return
        handle_update_restart()
        time.sleep(5)
    raise RuntimeError("MY-OK-WW: Auto login not finished within timeout")


def start_ok_and_game() -> OK:
    ok = start_ok()
    ensure_ok_and_game_ready(ok)
    auto_login(ok)
    return ok


def _get_task_error(task) -> str | None:
    localized_error_key = QCoreApplication.tr("app", "Error")
    err = task.info_get(localized_error_key)
    if not err and localized_error_key != "Error":
        err = task.info_get("Error")
    if isinstance(err, str):
        err = err.strip()
        return err or None
    return str(err) if err else None


def run_onetime_task(executor, task, *, timeout: int = 1800, poll_interval: int = 10) -> str:
    task.enable()
    task.unpause()
    start = time.time()
    while time.time() - start < timeout:
        if executor.exit_event.is_set():
            raise RuntimeError("Executor exit event set before task finished")
        if not task.enabled and executor.current_task is None:
            last_err = _get_task_error(task)
            task.running = False
            if last_err:
                return f"{task.name}: {last_err}"
            return ""
        time.sleep(poll_interval)
    raise TimeoutError(f"{task.name} did not finish within {timeout} seconds")


def run_onetime_task_until_time(
        executor,
        task,
        *,
        hour: int,
        minute: int = 0,
        poll_interval: int = 10) -> str:
    
    task.enable()
    task.unpause()

    deadline_ts = time.time() + minutes_until_target_time(target_hour=hour, target_minute=minute) * 60

    while True:
        if executor.exit_event.is_set():
            raise RuntimeError("Executor exit event set before task finished")
        if not task.enabled and executor.current_task is None:
            last_err = _get_task_error(task)
            task.running = False
            if last_err:
                return f"{task.name}: {last_err}"
            return ""
        if time.time() >= deadline_ts:
            task.disable()
            task.unpause()
            logger.info(f"到达设定时间，stopped {task.name} at {format_timestamp(now())}")
            return ""
        time.sleep(poll_interval)


def request_shutdown():
    """power off the machine via Windows shutdown."""
    subprocess.run(["shutdown.exe", "/s", "/t", "5"])


# region Read Data
def read_live_stamina(
    task: BaseWWTask,
    *,
    retries: int = 3,
    retry_sleep: float = 10.0,
) -> tuple[int | None, int | None]:
    """Open the stamina panel and return stamina."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                logger.info(f"MY-OK-WW: 重新尝试读取体力 ({attempt}/{retries})")
            task.ensure_main(esc=True, time_out=20)
            book_box = task.openF2Book("gray_book_boss")
            task.click_box(book_box, after_sleep=1)
            stamina, backup_stamina, _ = task.get_stamina()
            task.send_key("esc", after_sleep=1)
            if stamina < 0:
                logger.warning("MY-OK-WW: 读取体力失败")
            else:
                return stamina, backup_stamina
        except Exception as exc:
            last_exc = exc
            logger.warning(f"MY-OK-WW: 读取体力失败: {exc}")
        finally:
            task.ensure_main(esc=True, time_out=20)

        if attempt < retries:
            time.sleep(retry_sleep)

    if last_exc is not None:
        logger.error("MY-OK-WW: 读取体力失败，已超过最大重试次数", last_exc)
    else:
        logger.error("MY-OK-WW: 读取体力失败，已超过最大重试次数")
    return None, None


echo_number_re = re.compile(r'^(\d+)/3000$')
echo_overflow_prompt_re = re.compile(r"(2800|智能弃置)")


def read_echo_number(task: BaseWWTask, *, retries: int = 3, retry_sleep: float = 10.0, ocr_timeout: int = 5) -> int | None:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                logger.info(f"MY-OK-WW: 重新尝试读取声骸数量 ({attempt}/{retries})")
            task.ensure_main(esc=True, time_out=20)
            logger.info("MY-OK-WW: 按B打开背包")
            task.send_key('b')
            time.sleep(3)
            task.click_relative(0.04, 0.3)
            time.sleep(0.5)
            task.wait_click_ocr(
                box=task.box_of_screen(*get_ui_box("背包声骸数量上限取消按钮")),
                match="取消",
                time_out=ocr_timeout,
                raise_if_not_found=False,
                settle_time=0.2,
                after_sleep=0.5,
            )

            echo_number_box = task.wait_ocr(
                box=task.box_of_screen(*get_ui_box("背包声骸数量")),
                match=echo_number_re,
                raise_if_not_found=False,
                time_out=ocr_timeout,
                settle_time=0.5,
            )

            if echo_number_box:
                echo_number = int(echo_number_box[0].name.split('/')[0])
                logger.info(f"MY-OK-WW: 当前拥有 {echo_number} 声骸")
                return echo_number
            logger.warning("MY-OK-WW: 读取声骸数量识别失败")
        except Exception as exc:
            last_exc = exc
            logger.warning(f"MY-OK-WW: 读取声骸数量失败: {exc}")
        finally:
            task.ensure_main(esc=True, time_out=10)

        if attempt < retries:
            time.sleep(retry_sleep)

    if last_exc is not None:
        logger.error("MY-OK-WW: 读取声骸数量失败，已超过最大重试次数", last_exc)
    else:
        logger.error("MY-OK-WW: 读取声骸数量失败，已超过最大重试次数")
    return None

# endregion
