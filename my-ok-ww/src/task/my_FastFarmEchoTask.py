import time

from qfluentwidgets import FluentIcon

from ok import Logger, TaskDisabledException
from src.task.BaseCombatTask import BaseCombatTask
from src.task.WWOneTimeTask import WWOneTimeTask

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
        self.default_config.update({'Repeat Farm Count': 2000})
        # Exit combat once the boss health bar disappears.
        self.combat_end_condition = self._combat_over
        self._chars_initialized = False

    def run(self):
        WWOneTimeTask.run(self)
        self.use_liberation = False
        try:
            return self.do_run()
        except TaskDisabledException:
            pass

    def do_run(self):
        total = self.config.get('Repeat Farm Count', 0)
        for idx in range(total):
            self.log_info(f'战斗 {idx + 1}/{total}')
            if not self.wait_until(self.in_combat, time_out=30, raise_if_not_found=False):
                self.log_info('未检测到战斗，等待boss刷新')
                self.sleep(1)
                continue

            self.combat_once(wait_combat_time=60, raise_if_not_found=False)
            self._update_fight_rate()
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

    def _update_fight_rate(self):
        """
        Mirror FarmEchoTask's per-hour display: show fights/hour in the info panel.
        """
        fights = self.info.get('Combat Count', 0)
        self.info['Fights per Hour'] = round(fights / max(time.time() - self.start_time, 1) * 3600)
