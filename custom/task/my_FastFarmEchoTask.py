import time
from datetime import datetime

from qfluentwidgets import FluentIcon

from ok import Logger, TaskDisabledException
from custom.gsheet_manager import FastFarmResult, GoogleSheetClient
from src.task.BaseCombatTask import BaseCombatTask
from src.task.WWOneTimeTask import WWOneTimeTask
from custom.task.my_FiveToOneTask import FiveToOneTask

logger = Logger.get_logger(__name__)


class FastFarmEchoTask(WWOneTimeTask, BaseCombatTask):
    """
    Minimal fixed-position non-realm boss farm:
    - No character switching or post-fight movement
    - Echo pickup is just pressing the interact key after each kill
    - Supports multi-loop runs with per-loop reporting to Sheets
    """
    INFO_ORDER = ('Loop', 'Loop Fights', 'Fights per Hour', 'Remaining Time', 'Combat Count', 'Merge Count', 'Total Merge Count', 'Log')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "不切人快速刷取大世界4C"
        self.name = "4C速刷"
        self.group_name = "Farm"
        self.group_icon = FluentIcon.SYNC
        self.icon = FluentIcon.ALBUM
        self.default_config.update({
            'Repeat Farm Count': 2000,
            'Number of Loops': 1,
            'Run FiveToOne After Farm': True,
            'Exit After Task': False,
        })
        # Exit combat once the boss health bar disappears.
        self.combat_end_condition = self._combat_over
        self._chars_initialized = False
        self._loop_start_time = 0.0
        self._loop_end_time = 0.0
        self._run_start_time = 0.0
        self._last_error = ""
        self._any_reports_sent = False
        self._post_actions_executed = False
        self._loop_combat_baseline = 0
        self._loop_target_fights = 0

    def run(self):
        WWOneTimeTask.run(self)
        self.use_liberation = False
        self._run_start_time = time.time()
        self._loop_start_time = self._run_start_time
        self._loop_end_time = 0.0
        self._last_error = ""
        self._any_reports_sent = False
        self._post_actions_executed = False

        self.info_set("Total Merge Count", 0)
        self.info_set("Merge Count", 0)
        self.info_set("Combat Count", 0)
        self._ensure_info_layout()
        
        success = False
        exc_to_raise = None
        try:
            self.do_run()
            success = True
        except TaskDisabledException:
            # Do not treat TaskDisabledException as a failure.
            success = True
            self._last_error = ""
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            exc_to_raise = exc
        finally:
            self._loop_end_time = time.time()
            try:
                if not self._post_actions_executed:
                    self._post_run_actions(
                        farm_start=self._loop_start_time,
                        farm_end=self._loop_end_time,
                        success=success,
                        fight_count=int(self.info.get("Combat Count", 0) or 0),
                        fight_speed=int(self.info.get("Fights per Hour", 0) or 0),
                        report=not self._any_reports_sent,
                    )
            except Exception as exc:  # noqa: BLE001
                self.log_error("Post-run actions failed", exc)
                if success:
                    success = False
                if not self._last_error:
                    self._last_error = str(exc)
        if exc_to_raise:
            raise exc_to_raise

    def do_run(self):
        loops = max(int(self.config.get('Number of Loops', 1) or 1), 1)
        fights_per_loop = max(int(self.config.get('Repeat Farm Count', 1) or 1), 1)
        stop_after_disable = False
        self._loop_target_fights = fights_per_loop
        for loop_idx in range(loops):
            loop_number = loop_idx + 1
            self._start_loop(loop_number, loops, fights_per_loop)
            loop_success = False
            try:
                self._run_single_loop(loop_number, loops, fights_per_loop)
                loop_success = True
            except TaskDisabledException as exc:
                self.log_info(f"Task disabled, stopping after loop {loop_number}: {exc}")
                self._last_error = ""
                loop_success = True
                stop_after_disable = True
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                raise
            finally:
                self._finish_loop(loop_success)
            if stop_after_disable:
                break

    def _start_loop(self, loop_number: int, total_loops: int, fights_per_loop: int) -> None:
        """Reset per-loop counters and info display."""
        self._loop_start_time = time.time()
        self._last_error = ""
        self._loop_combat_baseline = int(self.info.get('Combat Count', 0) or 0)
        self.info_set('Merge Count', 0)
        self._prime_loop_info(loop_number, total_loops, fights_per_loop)

    def _prime_loop_info(self, loop_number: int, total_loops: int, fights_per_loop: int) -> None:
        """Seed loop-related info rows while keeping long-lived totals intact."""
        self.info_set('Loop', f"{loop_number}/{total_loops}")
        self.info_set('Loop Fights', f"0/{fights_per_loop}")
        self.info_set('Fights per Hour', 0)
        self.info_set('Remaining Time', "")
        self._ensure_info_layout()
        self._update_remaining_time(total_target=fights_per_loop)

    def _finish_loop(self, loop_success: bool) -> None:
        """Finalize a loop, including per-loop reporting and post-run hooks."""
        self._loop_end_time = time.time()
        loop_fights = self._current_loop_fights()
        loop_speed = int(self.info.get("Fights per Hour", 0) or 0)
        self._post_run_actions(
            farm_start=self._loop_start_time,
            farm_end=self._loop_end_time,
            success=loop_success,
            fight_count=loop_fights,
            fight_speed=loop_speed,
            report=True,
        )

    def _run_single_loop(self, loop_number: int, total_loops: int, fights_per_loop: int):
        self.log_info(f'开始循环 {loop_number}/{total_loops}，每轮战斗 {fights_per_loop} 次')
        self.run_until(self.in_combat, 'w', time_out=10, running=True)
        for idx in range(fights_per_loop):
            fight_number = idx + 1
            self.log_info(f'循环 {loop_number}/{total_loops} 战斗 {fight_number}/{fights_per_loop}')
            if not self.wait_until(self.in_combat, time_out=30, raise_if_not_found=False):
                self.log_info('未检测到战斗，等待boss刷新')
                self.sleep(1)
                continue

            self.combat_once(wait_combat_time=60, raise_if_not_found=False)
            self._update_fight_rate(total_target=fights_per_loop)
            self._pickup_echo()

    def _pickup_echo(self):
        self.wait_until(lambda: not self.in_combat(), time_out=5, raise_if_not_found=False)
        for _ in range(3):
            self.send_key('f', after_sleep=0.2)

    def _current_loop_fights(self) -> int:
        total = int(self.info.get('Combat Count', 0) or 0)
        return max(total - (self._loop_combat_baseline or 0), 0)

    def _update_fight_rate(self, total_target: int = 0) -> None:
        """
        Show fights/hour in the info panel using the current loop window.
        """
        loop_fights = self._current_loop_fights()
        elapsed = max(time.time() - (self._loop_start_time or self.start_time or time.time()), 1)
        self.info['Fights per Hour'] = round(loop_fights / elapsed * 3600)
        if total_target:
            self.info_set('Loop Fights', f"{loop_fights}/{total_target}")
        self._update_remaining_time(total_target=total_target)
        self._ensure_info_layout()

    def _update_remaining_time(self, total_target: int | None = None) -> None:
        total = int(total_target if total_target is not None else self._loop_target_fights)
        fights = self._current_loop_fights()
        if total <= 0 or fights <= 0:
            return
        remaining = max(total - fights, 0)
        elapsed = max(time.time() - (self._loop_start_time or self.start_time or time.time()), 1)
        seconds_per_fight = elapsed / fights
        remaining_seconds = remaining * seconds_per_fight
        hours = int(remaining_seconds // 3600)
        minutes = int((remaining_seconds % 3600) // 60)
        self.info['Remaining Time'] = f"{hours}h {minutes}m"
        self._ensure_info_layout()

    def _post_run_actions(
        self,
        *,
        farm_start: float,
        farm_end: float,
        success: bool,
        fight_count: int | None = None,
        fight_speed: int | None = None,
        report: bool = True,
    ):
        """
        Execute end-of-loop routines: revive wait, optional merge task, and sheet reporting.
        Intended to run after every loop; the outer run() only calls it once if a loop never started.
        """
        farm_start = farm_start or self._run_start_time or self.start_time or time.time()
        farm_end = farm_end or time.time()
        fight_count = int(fight_count if fight_count is not None else self._current_loop_fights())
        fight_speed = int(fight_speed if fight_speed is not None else (self.info.get("Fights per Hour", 0) or 0))
        loop_merge_count = int(self.info.get("Merge Count", 0) or 0)
        self._post_actions_executed = True
        # wait to die and revive
        self.log_info("开始等待复活")
        self.sleep(300)

        # Optionally run five-to-one task.
        if self.config.get('Run FiveToOne After Farm', True):
            self.ensure_main(time_out=120)
            self.sleep(2)
            try:
                self.run_task_by_class(FiveToOneTask)
                loop_merge_count = int(self.info.get("Merge Count", loop_merge_count) or loop_merge_count)
            except Exception as exc:  # noqa: BLE001
                self.log_error("FiveToOneTask failed", exc)
                success = False
                self._last_error = (self._last_error + "; " if self._last_error else "") + f"FiveToOneTask: {exc}"
        total_merge_count = int(self.info.get("Total Merge Count", 0) or 0) + loop_merge_count
        self.info_set("Total Merge Count", total_merge_count)
        if report:
            self._report_to_sheet(
                farm_start=farm_start,
                farm_end=farm_end,
                success=success,
                merge_count=loop_merge_count,
                fight_count=fight_count,
                fight_speed=fight_speed,
            )
            self._any_reports_sent = True

    def _report_to_sheet(
        self,
        farm_start: float,
        farm_end: float,
        success: bool,
        merge_count: int,
        fight_count: int | None = None,
        fight_speed: int | None = None,
    ):
        fight_count = int(fight_count if fight_count is not None else (self.info.get("Combat Count", 0) or 0))
        fight_speed = int(fight_speed if fight_speed is not None else (self.info.get("Fights per Hour", 0) or 0))
        result = FastFarmResult(
            started_at=datetime.fromtimestamp(farm_start),
            ended_at=datetime.fromtimestamp(farm_end),
            status="success" if success else "fail",
            fight_count=fight_count,
            fight_speed=fight_speed,
            merge_count=merge_count,
            error=self._last_error,
        )
        try:
            GoogleSheetClient().append_fast_farm_result(result)
            self.log_info("Reported run results to Google Sheet '5to1'")
        except Exception as exc:  # noqa: BLE001
            self.log_error("Report to Google Sheets failed", exc)

    def _ensure_info_layout(self) -> None:
        """
        Keep the info panel ordered and highlight loop/overall progress first.
        Retains any extra keys by appending them after the preferred order.
        """
        current = dict(self.info)
        reordered = {}
        for key in self.INFO_ORDER:
            if key in current:
                reordered[key] = current[key]
        for key, value in current.items():
            if key not in reordered:
                reordered[key] = value
        self.info.clear()
        self.info.update(reordered)


    # --- Combat/task overrides for fixed-position farming ---

    def in_combat(self):
        """
        Robust, non-blocking combat detection:
        - Only rely on health bar visibility (no retarget waits).
        - Keep a short grace window to avoid flapping when the bar flickers.
        """
        now = time.time()

        #if self.in_liberation or self.recent_liberation():
        #    return True

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
