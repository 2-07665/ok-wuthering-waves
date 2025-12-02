from __future__ import annotations

import time

from ok import Logger, og
from src.task.BaseWWTask import BaseWWTask
from src.task.WWOneTimeTask import WWOneTimeTask

from auto import ensure_game_running

logger = Logger.get_logger(__name__)


class BootstrapMainTask(WWOneTimeTask, BaseWWTask):
    """One-time task to ensure the game is running and in the main world."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Bootstrap Main"
        self.group_name = "Bootstrap"
        self.group_icon = None
        self.icon = None
        self.supported_languages = []
        self.default_config = {
            "Main Timeout": 600,
            "Start Timeout": 120,
        }

    def run(self):
        WWOneTimeTask.run(self)

        dm = self.executor.device_manager
        start_timeout = self.config.get("Start Timeout", self.executor.config.get("start_timeout", 120))
        main_timeout = self.config.get("Main Timeout", self.executor.config.get("main_timeout", 600))
        retry_timeout = min(main_timeout, 180)

        if self._attempt_main(main_timeout):
            self.log_info("Reached main screen")
            return

        self.log_warning("Main screen not reached; restarting game once.")
        try:
            dm.stop_hwnd()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to stop game before restart", exc)
        time.sleep(5)

        ensure_game_running(og.ok, timeout=start_timeout)
        
        if self._attempt_main(retry_timeout):
            self.log_info("Reached main screen after restart")
            return

        raise Exception("Failed to reach main screen after restart")

    def _attempt_main(self, total_timeout: int) -> bool:
        try:
            self.ensure_main(time_out=total_timeout, esc=True)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to reach main within timeout: {exc}")
            return False
