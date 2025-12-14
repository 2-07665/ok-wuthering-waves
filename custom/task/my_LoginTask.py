from __future__ import annotations

import re
import time

from qfluentwidgets import FluentIcon

from ok import Logger, og
from src.task.BaseWWTask import BaseWWTask
from src.task.WWOneTimeTask import WWOneTimeTask

from custom.auto import ensure_game_running

logger = Logger.get_logger(__name__)


class LoginTask(WWOneTimeTask, BaseWWTask):
    """One-time task to login."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Login"
        self.group_name = "Login"
        self.group_icon = FluentIcon.HOME
        self.icon = FluentIcon.HOME
        self.default_config = {
            "Login Timeout": 180,
        }
        self._restart_wait_until = 0

    def run(self):
        WWOneTimeTask.run(self)
        login_timeout = self.config.get("Login Timeout", self.executor.config.get("login_timeout", 180))

        self.log_info("MY-OK-WW: Start login flow")
        self._ensure_capture_ready()
        if not self.auto_login(login_timeout):
            raise Exception("MY-OK-WW: Failed to reach main screen in first try")
        self.log_info("MY-OK-WW: Login flow finished, verifying main state")
        self.ensure_main(time_out=30, esc=True)

    def auto_login(self, total_timeout: int) -> bool:
        start = time.time()
        self.info_set("current task", "auto login")
        while time.time() - start < total_timeout:
            if self.in_team_and_world():
                self._logged_in = True
                return True
            if self.handle_update_restart():
                continue
            if self.wait_login():
                return True
            self._ensure_capture_ready()
            self.sleep(3)
        return False

    def handle_update_restart(self) -> bool:
        notice = self.wait_ocr(
            0.15,
            0.25,
            to_x=0.85,
            to_y=0.75,
            match=[re.compile("更新完成"), re.compile("重启")],
            time_out=5,
            raise_if_not_found=False,
            settle_time=0.5,
        )
        if not notice:
            return False
        self.log_info("MY-OK-WW: Detected update completion prompt, confirming restart")
        confirm_regions = [
            (0.55, 0.58, 0.78, 0.72),  # tight around expected confirm button
            (0.45, 0.55, 0.80, 0.78),  # slightly wider fallback
        ]
        confirmed = None
        for x, y, to_x, to_y in confirm_regions:
            confirmed = self.wait_click_ocr(
                x,
                y,
                to_x=to_x,
                to_y=to_y,
                match="确认",
                time_out=6,
                raise_if_not_found=False,
                settle_time=0.15,
                after_sleep=1.2,
            )
            if confirmed:
                break
        if not confirmed:
            self.click_relative(0.67, 0.65, after_sleep=1.5)
        self.sleep(3)
        self._restart_wait_until = time.time() + 90  # allow the client to restart without re-launching
        self._ensure_capture_ready(allow_launch=False, timeout=60)
        return True

    def _ensure_capture_ready(self, allow_launch: bool | None = None, timeout: int = 120) -> bool:
        if allow_launch is None:
            allow_launch = time.time() >= self._restart_wait_until

        dm = self.executor.device_manager
        end_time = time.time() + timeout
        while time.time() < end_time:
            dm.do_refresh(True)
            preferred = dm.get_preferred_device()
            connected = bool(preferred and preferred.get("connected"))
            capture_ready = dm.capture_method is not None and dm.capture_method.connected()
            interaction_ready = dm.interaction is not None
            if capture_ready and interaction_ready:
                return True
            if connected:
                dm.do_start()  # ensure capture/interaction are reinitialized for the existing window
            elif allow_launch:
                try:
                    ensure_game_running(og.ok, timeout=int(max(10, end_time - time.time())))
                    return True
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"MY-OK-WW: Failed to ensure game running after restart: {exc}")
            self.sleep(2)
        logger.warning("MY-OK-WW: Capture/interaction not ready after restart wait")
        return False
