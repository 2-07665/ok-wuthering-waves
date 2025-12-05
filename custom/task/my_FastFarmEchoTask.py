import time
from datetime import datetime

from qfluentwidgets import FluentIcon

from ok import Logger, TaskDisabledException
from src.task.BaseCombatTask import BaseCombatTask
from src.task.WWOneTimeTask import WWOneTimeTask
from custom.task.my_FiveToOneTask import FiveToOneTask

logger = Logger.get_logger(__name__)


class FastFarmEchoTask(WWOneTimeTask, BaseCombatTask):
    """
    Minimal fixed-position non-realm boss farm:
    - No character switching or post-fight movement
    - Echo pickup is just pressing the interact key after each kill
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "单人速刷位置固定的4C Boss"
        self.name = "固定4C速刷"
        self.group_name = "Farm"
        self.group_icon = FluentIcon.SYNC
        self.icon = FluentIcon.ALBUM
        self.default_config.update({
            'Repeat Farm Count': 2000,
            'Run FiveToOne After Farm': True,
            'Exit After Task': False,
        })
        # Exit combat once the boss health bar disappears.
        self.combat_end_condition = self._combat_over
        self._chars_initialized = False
        self._farm_start_time = 0.0
        self._farm_end_time = 0.0
        self._last_error = ""

    def run(self):
        WWOneTimeTask.run(self)
        self.use_liberation = False
        self._farm_start_time = time.time()
        self._farm_end_time = 0.0
        self._last_error = ""
        self.info_set("total merge count", 0)
        success = False
        exc_to_raise = None
        try:
            self.do_run()
            success = True
        except TaskDisabledException as exc:
            self._last_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            exc_to_raise = exc
        finally:
            self._farm_end_time = time.time()
            try:
                self._post_run_actions(success)
            except Exception as exc:  # noqa: BLE001
                self.log_error("Post-run actions failed", exc)
                if success:
                    success = False
                if not self._last_error:
                    self._last_error = str(exc)
        if exc_to_raise:
            raise exc_to_raise

    def do_run(self):
        total = self.config.get('Repeat Farm Count', 0)
        for idx in range(total):
            self.log_info(f'战斗 {idx + 1}/{total}')
            if not self.wait_until(self.in_combat, time_out=30, raise_if_not_found=False):
                self.log_info('未检测到战斗，等待boss刷新')
                self.sleep(1)
                continue

            self.combat_once(wait_combat_time=60, raise_if_not_found=False)
            self._update_fight_rate(total)
            self._pickup_echo()

    def _pickup_echo(self):
        self.wait_until(lambda: not self.in_combat(), time_out=5, raise_if_not_found=False)
        for _ in range(3):
            self.send_key('f', after_sleep=0.2)

    def in_combat(self):
        """
        Robust, non-blocking combat detection:
        - Only rely on health bar visibility (no retarget waits).
        - Keep a short grace window to avoid flapping when the bar flickers.
        """
        now = time.time()

        if self.in_liberation or self.recent_liberation():
            return True

        if self.check_health_bar():
            self._in_combat = True
            self.last_combat_check = now
            return True

        if self._in_combat:
            if self.combat_end_condition and self.combat_end_condition():
                return self.reset_to_false(recheck=False, reason='end condition reached')
            if now - self.last_combat_check < 0.8:
                return True
        return False

    def target_enemy(self, wait=True):
        """
        Skip long retarget waits so actions keep flowing even if the lock briefly drops.
        """
        if self.has_target():
            return True
        self.middle_click()
        return True

    def switch_next_char(self, current_char, *args, **kwargs):
        return current_char

    def check_combat(self):
        """
        Never raise out of combat; keep the loop running to avoid freezes.
        """
        return True

    def sleep_check_combat(self, timeout, check_combat=True):
        """
        Disable combat guard during skill waits so HP-bar flicker or a kill at the
        end of an animation can't break the loop.
        """
        self.sleep(timeout)

    def load_chars(self):
        """
        Detect team once and reuse to avoid repeated team-size changes or resets.
        """
        if self._chars_initialized and any(self.chars):
            for char in self.chars:
                if char:
                    char.is_current_char = True
            return True

        loaded = super().load_chars()
        self._chars_initialized = True
        return loaded

    def _combat_over(self):
        return not self.check_health_bar()

    def _update_fight_rate(self, total_target: int = 0):
        """
        Mirror FarmEchoTask's per-hour display: show fights/hour in the info panel.
        """
        fights = self.info.get('Combat Count', 0)
        self.info['Fights per Hour'] = round(fights / max(time.time() - self.start_time, 1) * 3600)
        self._update_remaining_time()

    def _update_remaining_time(self):
        total = int(self.config.get('Repeat Farm Count', 0) or 0)
        fights = int(self.info.get('Combat Count', 0) or 0)
        if total <= 0 or fights <= 0:
            return
        remaining = max(total - fights, 0)
        elapsed = max(time.time() - (self._farm_start_time or self.start_time), 1)
        seconds_per_fight = elapsed / fights
        remaining_seconds = remaining * seconds_per_fight
        hours = int(remaining_seconds // 3600)
        minutes = int((remaining_seconds % 3600) // 60)
        self.info['Remaining Time'] = f"{hours}h {minutes}m"

    def _post_run_actions(self, success: bool):
        farm_start = self._farm_start_time or self.start_time or time.time()
        farm_end = self._farm_end_time or time.time()
        merge_count = self.info.get("total merge count", 0)
        # Teleport to a safe point via F2 book.
        try:
            self._teleport_to_safe_point()
        except Exception as exc:  # noqa: BLE001
            self.log_error("Teleport to safe point failed", exc)
            success = False
            self._last_error = self._last_error or f"Teleport failed: {exc}"
        # Optionally run five-to-one task.
        if self.config.get('Run FiveToOne After Farm', True):
            # Give the game time to finish loading after teleport.
            self.wait_in_team_and_world(time_out=120, raise_if_not_found=False)
            self.sleep(5)
            try:
                self.run_task_by_class(FiveToOneTask)
                merge_count = self.info.get("total merge count", merge_count)
            except Exception as exc:  # noqa: BLE001
                self.log_error("FiveToOneTask failed", exc)
                success = False
                self._last_error = (self._last_error + "; " if self._last_error else "") + f"FiveToOneTask: {exc}"
        # Report results without counting FiveToOne duration.
        self._report_to_sheet(
            farm_start=farm_start,
            farm_end=farm_end,
            success=success,
            merge_count=merge_count,
        )

    def _teleport_to_safe_point(self):
        gray_book_boss = self.openF2Book("gray_book_boss")
        self.click_box(gray_book_boss, after_sleep=1)
        # Open Tacet tab and teleport to the first entry as a safe point.
        self.click_relative(0.18, 0.48, after_sleep=1)
        self.click_on_book_target(1, 12)
        self.wait_click_travel()
        self.wait_in_team_and_world(time_out=120, raise_if_not_found=False)

    def _report_to_sheet(self, farm_start: float, farm_end: float, success: bool, merge_count: int):
        fight_count = int(self.info.get("Combat Count", 0) or 0)
        fight_speed = self.info.get("Fights per Hour", 0)
        duration_seconds = max(farm_end - farm_start, 0)
        duration_minutes = int(duration_seconds // 60)
        duration_hours = int(duration_minutes // 60)
        duration_minutes = duration_minutes % 60
        duration_str = f"{duration_hours}h {duration_minutes}m"
        start_str = datetime.fromtimestamp(farm_start).strftime("%Y-%m-%d %H:%M:%S")
        end_str = datetime.fromtimestamp(farm_end).strftime("%Y-%m-%d %H:%M:%S")
        status = "success" if success else "fail"
        error_info = self._last_error
        try:
            import gspread  # type: ignore

            sheet_id = self._read_sheet_id()
            if not sheet_id:
                self.log_error("No Google Sheet ID found", None)
                return
            client = gspread.service_account(filename="credentials/google-api.json")
            sh = client.open_by_key(sheet_id)
            ws = sh.worksheet("5to1")
            ws.append_row(
                [
                    start_str,
                    end_str,
                    duration_str,
                    status,
                    fight_count,
                    fight_speed,
                    merge_count,
                    error_info,
                ],
                value_input_option="USER_ENTERED",
            )
            self.log_info("Reported run results to Google Sheet '5to1'")
        except Exception as exc:  # noqa: BLE001
            self.log_error("Report to Google Sheets failed", exc)

    def _read_sheet_id(self) -> str:
        try:
            with open("credentials/google-sheet-id.txt", "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""
