import time
from src.char.BaseChar import BaseChar

class Aemeath(BaseChar):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def one_shot(self):
        if self.has_long_action():
            self.use_enhanced_heavy()
            time.sleep(2)

    def fight(self):
        if self.enhanced_e_available():
            self.send_resonance_key()
            time.sleep(4)
        
        self.click()
        time.sleep(0.2)
        self.click()
        time.sleep(0.2)
        self.click()
        time.sleep(0.2)

    def enhanced_e_available(self):
        return (self.task.find_one('aemeath_e1', threshold=0.7) or
                self.task.find_one('aemeath_e2', threshold=0.7))
        
    def use_enhanced_heavy(self):
        self.task.mouse_down()
        self.task.wait_until(lambda: not self.has_long_action, time_out=1.2)
        self.task.mouse_up()

    def post_fight(self):
        pass