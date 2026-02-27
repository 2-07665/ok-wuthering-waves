import time
from src.char.BaseChar import BaseChar

class Cartethyia(BaseChar):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_sword1 = False # heavy
        #self.has_sword2 = False # a4
        self.has_sword3 = False # skill

    def one_shot(self):
        if self.has_sword3:
            self.task.jump(after_sleep=0.3)
            self.click()
            self.has_sword1 = False
            self.has_sword3 = False
            return
        if self.resonance_available():
            self.send_resonance_key()
            time.sleep(0.4)
            self.click()
            self.has_sword1 = False
            self.has_sword3 = False

    def fight(self):
        self.click()
        time.sleep(0.2)
        self.click()
        time.sleep(0.2)
        self.click()
        time.sleep(0.2)
    
    def post_fight(self):
        if self.resonance_available():
            self.send_resonance_key()
            time.sleep(0.4)
            self.has_sword3 = True

        if not self.has_sword1:
            self.task.mouse_down()
            time.sleep(0.4)
            self.task.mouse_up()
            self.has_sword1 = True

