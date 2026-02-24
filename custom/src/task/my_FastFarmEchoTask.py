import time

from qfluentwidgets import FluentIcon
from ok import Logger
logger = Logger.get_logger(__name__)
from src.task.BaseCombatTask import BaseCombatTask


class FastFarmEchoTask(BaseCombatTask):
    """Fixed-position fast boss farm with single-character combat."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "单人速刷位置固定的4C Boss"
        self.name = "固定4C速刷"
        self.group_name = "My"
        self.group_icon = FluentIcon.SYNC
        self.icon = FluentIcon.ALBUM
        self.default_config = {"Repeat Farm Count": 2000}
        self.combat_grace_window = 0.8
        self.last_combat_check = 0
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
        self.send_key('f', after_sleep=0.3)
        self.send_key('f', after_sleep=0.3)

# region Combat Overwrite
    def in_combat(self, target=False):
        """Health-bar-only combat check with short flicker tolerance."""
        now = time.time()
        if self.check_health_bar():
            self._in_combat = True
            self.last_combat_check = now
            return True

        if self._in_combat:
            if now - self.last_combat_check < self.combat_grace_window:
                return True
            return self.reset_to_false(reason='health bar missing')
        return False

    def switch_next_char(self, current_char, *args, **kwargs):
        return current_char

    def sleep_check(self):
        """Refresh combat state during sleep without raising."""
        if self._in_combat:
            self.next_frame()
            self.in_combat()

    def check_combat(self):
        """Do not raise during short respawn gaps."""
        self.in_combat()

    def combat_end(self):
        """Skip per-character end hooks that can trigger switching."""
        return

    def load_chars(self):
        """Force single-char logic while keeping upstream slot indexing safe."""
        loaded = super().load_chars()
        if not loaded:
            return loaded
        current = self.get_current_char(raise_exception=False)
        if current is None:
            return loaded
        self.chars = [current] * max(2, len(self.chars))
        return True
# endregion
