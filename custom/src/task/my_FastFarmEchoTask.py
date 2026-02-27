import time
from qfluentwidgets import FluentIcon

from ..char.Cartethyia import Cartethyia
from ..char.Aemeath import Aemeath
from src.task.BaseCombatTask import BaseCombatTask


class FastFarmEchoTask(BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "单人速刷位置固定的4C"
        self.name = "固定4C速刷"
        self.group_name = "My"
        self.group_icon = FluentIcon.SYNC
        self.icon = FluentIcon.ALBUM
        self.default_config = {"刷多少次": 2000, "角色": 1}

        self.combat_check_grace_window = 1.0
        self.last_combat_check = 0
        
    def run(self):
        farm_target = self.config.get("刷多少次", 0)
        char_id = self.config.get("角色", 1)
        self.info_set("Fight Count", 0)

        self.ensure_main(esc=True, time_out= 60)
        self.load_fixed_char(char_id)
        self.run_until(self.simple_in_combat, "w", time_out=10, running=True)

        for idx in range(farm_target):
            self.log_info(f"战斗: {idx + 1}/{farm_target}")
            self.my_farm_once()
            self.info_incr("Fight Count", 1)

    def simple_pickup_echo(self):
        self.send_key('f', after_sleep=0.3)
        time.sleep(2.4)

# region Combat
    def my_farm_once(self):
        self.wait_until(self.simple_in_combat, time_out=300, raise_if_not_found=False)
        self._fixed_char.one_shot()
        while self.simple_in_combat():
            self._fixed_char.fight()

        self.simple_pickup_echo()
        self._fixed_char.post_fight()

    def simple_in_combat(self):
        now = time.time()
        if self.check_health_bar():
            self._in_combat = True
            self.last_combat_check = now
            return True
        if self._in_combat:
            if now - self.last_combat_check < self.combat_check_grace_window:
                return True
        self._in_combat = False
        return False

    def load_fixed_char(self, char_id):
        self.load_hotkey()

        if char_id == 1:
            self._fixed_char = Cartethyia(self, 0,
                    res_cd=14,
                    echo_cd=25,
                    liberation_cd=20,
                    char_name="char_cartethyia",
                    confidence=1,
                    ring_index=4,
                )
        else:
            self._fixed_char = Aemeath(self, 0,
                    res_cd=4,
                    echo_cd=25,
                    liberation_cd=25,
                    char_name="char_aemeath",
                    confidence=1,
                    ring_index=2,
                )
        c = self._fixed_char
        c.is_current_char = True
        self.chars = [c]
# endregion
