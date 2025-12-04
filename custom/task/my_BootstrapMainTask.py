from __future__ import annotations

from ok import Logger
from src.task.BaseWWTask import BaseWWTask
from src.task.WWOneTimeTask import WWOneTimeTask

from custom.auto import ensure_game_running

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
            "Main Timeout": 120,
        }

    def run(self):
        WWOneTimeTask.run(self)
        main_timeout = self.config.get("Main Timeout", self.executor.config.get("main_timeout", 120))

        if self._attempt_main(main_timeout):
            self.log_info("Reached main screen")
            return
        raise Exception("Failed to reach main screen after restart")

    def _attempt_main(self, total_timeout: int) -> bool:
        try:
            self.ensure_main(time_out=total_timeout, esc=True)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to reach main within timeout: {exc}")
            return False
