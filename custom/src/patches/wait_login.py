import re
from functools import wraps

from src.task.BaseWWTask import BaseWWTask


def patch_basewwtask_wait_login_disable_restart() -> None:
    if getattr(BaseWWTask, "_my_patch_wait_login_disable_restart", False):
        return

    original_wait_login = BaseWWTask.wait_login

    @wraps(original_wait_login)
    def wait_login_without_restart(self):
        if not self._logged_in:
            if self.find_one('login_account', vertical_variance=0.1, threshold=0.7):
                self.wait_until(lambda: self.find_one('login_account', threshold=0.7) is None,
                                pre_action=lambda: self.click_relative(0.5, 0.9, after_sleep=3), time_out=30)
                self.wait_until(lambda: self.find_one('monthly_card', threshold=0.7) or self.in_team_and_world(),
                                pre_action=lambda: self.click_relative(0.5, 0.9, after_sleep=3), time_out=120)
                self.wait_until(lambda: self.in_team_and_world(),
                                post_action=lambda: self.click_relative(0.5, 0.9, after_sleep=3), time_out=5)
                self.log_info('Auto Login Success', notify=True)
                self._logged_in = True
                self.sleep(3)
                return True
            texts = self.ocr()
            if login := self.find_boxes(texts, boundary=self.box_of_screen(0.3, 0.3, 0.7, 0.7), match="登录"):
                if not self.find_boxes(texts, match="+86"):
                    self.click(login)
                    self.log_info('点击登录按钮!')
                return False
            # deleted lines for handling update restart
            if start := self.find_boxes(texts, boundary='bottom_right', match=["开始游戏", re.compile("进入游戏")]):
                if not self.find_boxes(texts, boundary='bottom_right', match="登录"):
                    self.click(start)
                    self.log_info(f'点击开始游戏! {start}')
                    return False

    BaseWWTask._my_patch_wait_login_disable_restart = True
    BaseWWTask._my_patch_wait_login_original = original_wait_login
    BaseWWTask.wait_login = wait_login_without_restart
