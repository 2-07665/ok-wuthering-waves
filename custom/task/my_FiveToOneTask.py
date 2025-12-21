import re

from qfluentwidgets import FluentIcon

from ok import Logger
logger = Logger.get_logger(__name__)

from src.task.BaseWWTask import BaseWWTask
from custom.ui_boxes import get_ui_box


class FiveToOneTask(BaseWWTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "自动五合一未锁定声骸"
        self.name = "数据坞五合一"
        self.group_name = "My"
        self.group_icon = FluentIcon.SYNC
        self.icon = FluentIcon.ALBUM
        self.default_config = {}

    def run(self):
        self.log_info("开始五合一任务")
        self.info_set("Merge Count", 0)
        self.ensure_main(esc=True, time_out=30)
        self.log_info("在主页")
        self.open_esc_menu()
        self.sleep(1.0)
        ocr_result = self.wait_click_ocr(*get_ui_box("ESC菜单数据坞"), match="数据坞", time_out=20, raise_if_not_found=True, settle_time=0.2, after_sleep=1.0)
        if ocr_result is None:
            self.screenshot(name="未找到ESC菜单数据坞")
        self.wait_ocr(*get_ui_box("数据坞左上角判断"), match="数据坞", time_out=20, raise_if_not_found=True, settle_time=0.2)
        self.click_relative(0.04, 0.56, after_sleep=1.0)
        self.loop_merge()
        self.ensure_main(esc=True, time_out=30)
        self.log_info("五合一完成!")

    def loop_merge(self):
        """
        Enter batch merge, select all, consume merges until no merges remain.
        """
        while True:
            if not self.wait_click_ocr(*get_ui_box("数据坞批量融合入口"), match="批量融合", time_out=10, raise_if_not_found=False, settle_time=0.2, after_sleep=1.0):
                self.log_info("MY-OK-WW: 未找到批量融合入口，结束任务")
                return

            if not self.wait_click_ocr(*get_ui_box("数据坞批量融合全选"), match="全选", time_out=5, raise_if_not_found=False, settle_time=0.2, after_sleep=1.0):
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

            if not self.wait_click_ocr(*get_ui_box("数据坞批量融合按钮"), match="批量融合", time_out=5, raise_if_not_found=False, settle_time=0.2, after_sleep=1.0):
                self.log_info("MY-OK-WW: 未找到批量融合按钮，结束任务")
                return

            self.wait_click_ocr(*get_ui_box("数据坞批量融合确认按钮"), match="确认", time_out=2, raise_if_not_found=False, settle_time=0.2, after_sleep=1.0)
            self.wait_ocr(*get_ui_box("数据坞批量融合获得声骸"), match="获得", time_out=5, raise_if_not_found=False, settle_time=1.0)
            self.info_incr("Merge Count", merge_count)
            self.click_relative(0.5, 0.05, after_sleep=1.0)

    def _read_merge_count(self):
        """
        Read the current merge count from the bottom-right text "数据融合次数：num".
        """
        result = self.ocr(*get_ui_box("数据坞数据融合次数"), match=re.compile(r"数据融合次数[:：]\s*\d+"))
        if not result:
            return None
        match = re.search(r"数据融合次数[:：]\s*(\d+)", result[0].name)
        if not match:
            return None
        
        try:
            return int(match.group(1))
        except ValueError:
            return None
