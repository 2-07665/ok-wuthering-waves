import re

from qfluentwidgets import FluentIcon

from ok import Logger
logger = Logger.get_logger(__name__)

from src.task.BaseCombatTask import BaseCombatTask


class FiveToOneTask(BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "自动五合一未锁定声骸"
        self.name = "数据坞五合一"
        self.group_name = "My"
        self.group_icon = FluentIcon.SYNC
        self.icon = FluentIcon.ALBUM
        self.default_config = {}

        self.merge_count_box = None
        self.merge_button_box = None
        self.confirm_box = None

    def run(self):
        self.merge_count_box = self.box_of_screen(0.677, 0.841, 0.895, 0.885)
        self.merge_button_box = self.box_of_screen(0.658, 0.880, 0.916, 0.946)
        self.confirm_box = self.box_of_screen(0.59, 0.59, 0.75, 0.66)

        self.log_info("开始五合一任务")
        self.info_set("Merge Count", 0)
        self.ensure_main(esc=True, time_out=30)
        self.log_info("在主页")
        self.sleep(0.5)
        self.open_esc_menu()
        self.wait_click_ocr(match="数据坞", box="right", time_out=20, raise_if_not_found=True, settle_time=0.2, after_sleep=1.0)
        self.wait_ocr(x=0, y=0, to_x=0.15, to_y=0.12, match="数据坞", time_out=20, raise_if_not_found=True, settle_time=0.2)
        self.click_relative(0.04, 0.56, after_sleep=1.0)
        self.loop_merge()
        self.ensure_main(esc=True, time_out=30)
        self.log_info("五合一完成!")

    def loop_merge(self):
        """
        Enter batch merge, select all, consume merges until no merges remain.
        """
        while True:
            if not self.wait_click_ocr(match="批量融合", box="right", time_out=10, raise_if_not_found=False, settle_time=0.2, after_sleep=1.0):
                self.log_info("MY-OK-WW: 未找到批量融合入口，结束任务")
                return

            if not self.wait_click_ocr(match="全选", box="bottom_left", time_out=5, raise_if_not_found=False, settle_time=0.2, after_sleep=1.0):
                self.log_info("MY-OK-WW: 未找到全选按钮，结束任务")
                return

            merge_count = self._read_merge_count()
            if merge_count is None:
                self.log_info("MY-OK-WW: 无法识别数据融合次数，结束任务")
                return
            self.info_set("Remaining Merge Count", merge_count)
            if merge_count == 0:
                self.log_info("MY-OK-WW: 未锁定声骸已耗尽，结束任务")
                return

            if not self.wait_click_ocr(match="批量融合", box=self.merge_button_box, time_out=5, raise_if_not_found=False, settle_time=0.2, after_sleep=1.0):
                self.log_info("MY-OK-WW: 未找到批量融合按钮，结束任务")

            self.wait_click_ocr(match="确认", box=self.confirm_box, time_out=2, raise_if_not_found=False, settle_time=0.2, after_sleep=1.0)
            self.wait_ocr(match="获得声骸", box="top", time_out=5, raise_if_not_found=False, settle_time=1.0)
            self.info_incr("Merge Count", merge_count)
            self.click_relative(0.53, 0.05, after_sleep=1.0)

    def _read_merge_count(self):
        """
        Read the current merge count from the bottom-right text "数据融合次数：num".
        """
        result = self.ocr(match=re.compile(r"数据融合次数[:：]\s*\d+"), box=self.merge_count_box)
        if not result:
            return None
        match = re.search(r"数据融合次数[:：]\s*(\d+)", result[0].name)
        if not match:
            return None
        
        try:
            return int(match.group(1))
        except ValueError:
            return None
