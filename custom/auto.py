from config import config
from ok import OK, Logger, execute
import custom.log_filter
logger = Logger.get_logger(__name__)

from src.task.BaseWWTask import BaseWWTask

import subprocess

import time
from custom.gsheet_manager import RunResult


# region Manage OK
def request_shutdown():
    """power off the machine via Windows shutdown."""
    subprocess.run(["shutdown.exe", "/s", "/t", "5"])


def bootstrap_ok() -> OK:
    config["use_gui"] = False
    ok = OK(config)
    ensure_game_running(ok)
    return ok


def ensure_game_running(ok: OK, timeout: int = 120) -> None:
    """Start the game if needed and wait until capture/interaction are ready."""
    dm = ok.device_manager
    dm.do_refresh(True)
    preferred = dm.get_preferred_device()

    if not preferred.get("connected"):
        path = dm.get_exe_path(preferred)
        logger.info(f"MY-OK-WW: Launching game from {path}")
        execute(path)

    start = time.time()
    while time.time() - start < timeout:
        dm.do_refresh(True)
        preferred = dm.get_preferred_device()
        capture_ready = (
            preferred
            and preferred.get("connected")
            and dm.capture_method is not None
            and dm.capture_method.connected()
        )
        interaction_ready = dm.interaction is not None
        if capture_ready and interaction_ready:
            return
        time.sleep(4)
    raise RuntimeError("MY-OK-WW: Game window not ready within timeout.")


def run_onetime_task(executor, task, *, timeout: int = 1800) -> None:
    task.enable()
    task.unpause()
    start = time.time()
    while time.time() - start < timeout:
        if executor.exit_event.is_set():
            raise RuntimeError("Executor exit event set before task finished.")
        if not task.enabled and executor.current_task is None:
            if err := task.info.get("Error"):
                raise RuntimeError(err)
            task.running = False
            return
        time.sleep(1)
    raise TimeoutError(f"{task.name} did not finish within {timeout} seconds.")
# endregion


# region Stamina
def fill_used_stamina(result: RunResult) -> None:
    """Calculate and fill stamina_used from start/left totals."""
    if (None in (result.stamina_start, result.backup_stamina_start, result.stamina_left, result.backup_stamina_left)):
        return
    start_total = (result.stamina_start or 0) + (result.backup_stamina_start or 0)
    end_total = (result.stamina_left or 0) + (result.backup_stamina_left or 0)
    consumed = max(0, start_total - end_total)
    result.stamina_used = int(round(consumed / 10.0)) * 10


def read_live_stamina(ok: OK, task: BaseWWTask) -> tuple[int | None, int | None]:
    """Open the stamina panel and return stamina."""
    try:
        task.ensure_main(time_out = 60, esc = True)
        book_box = task.openF2Book("gray_book_boss")
        task.click_box(book_box, after_sleep = 1)
        stamina, backup_stamina, _ = task.get_stamina()
        task.send_key("esc", after_sleep = 1)
        if stamina < 0:
            return None, None
        return stamina, backup_stamina
    except Exception as exc:
        logger.error("MY-OK-WW: Failed to read live stamina", exc)
        return None, None
# endregion
