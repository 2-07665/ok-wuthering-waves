import time

from qfluentwidgets import FluentIcon

from ok import Logger
from src.task.BaseCombatTask import BaseCombatTask

logger = Logger.get_logger(__name__)


class FastFarmEchoTask(BaseCombatTask):
    """
    Minimal fixed-position non-realm boss farm:
    - No character switching or post-fight movement
    - Echo pickup is just pressing the interact key after each kill
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "单人速刷位置固定的4C Boss"
        self.name = "固定4C速刷"
        self.group_name = "My"
        self.group_icon = FluentIcon.SYNC
        self.icon = FluentIcon.ALBUM
        self.default_config = {"Repeat Farm Count": 2000}
        # Exit combat once the boss health bar disappears.
        self.combat_end_condition = self._combat_over
        self._chars_initialized = False

        self.use_liberation = False

    def run(self):
        farm_target = self.config.get('Repeat Farm Count', 0)
        self.info_set("Fight Count", 0)

        self.ensure_main(esc=True, time_out= 60)
        self.run_until(self.in_combat, 'w', time_out=10, running=True)

        for idx in range(farm_target):
            self.log_info(f'战斗: {idx + 1}/{farm_target}')
            self.combat_once(wait_combat_time=300, raise_if_not_found=False)
            self._pickup_echo()
            self.info_incr("Fight Count", 1)

        logger.info(f"MY-OK-WW: {farm_target} 次战斗已完成")
        self.info_set("Fight Count", farm_target)

    def _pickup_echo(self):
        for _ in range(3):
            self.send_key('f', after_sleep=0.3)


# region Combat Overwrite
    def in_combat(self):
        """
        Robust, non-blocking combat detection:
        - Only rely on health bar visibility (no retarget waits).
        - Keep a short grace window to avoid flapping when the bar flickers.
        """
        now = time.time()

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
        pass

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
# endregion
