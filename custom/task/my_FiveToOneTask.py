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
        self.default_config = {
        }

    def run(self):
        self.log_info("开始五合一任务")
        self.info_set("Merge Count", 0)
        self.ensure_main(esc=True, time_out=30)
        self.log_info("在主页")
        self.sleep(0.5)
        self.open_esc_menu()
        self.wait_click_ocr(match="数据坞", box="right", raise_if_not_found=True, settle_time=0.2)
        self.wait_ocr(match="数据坞", box="top_left", raise_if_not_found=True, settle_time=0.2)
        self.click_relative(0.04, 0.56, after_sleep=0.5)
        self.loop_merge()
        self.ensure_main()
        self.log_info("五合一完成!")

    def loop_merge(self):
        """
        Enter batch merge, select all, consume merges until no merges remain.
        """
        while True:
            if not self.wait_click_ocr(match="批量融合", box="right", raise_if_not_found=False, settle_time=0.2,
                                           after_sleep=0.5):
                self.log_info("未找到批量融合入口，结束任务")
                return

            if not self.wait_click_ocr(match="全选", box="bottom_left", raise_if_not_found=False, settle_time=0.2,
                                       after_sleep=0.3):
                self.log_info("未找到全选按钮，结束任务")
                return

            merge_count = self._read_merge_count()
            if merge_count is None:
                self.log_info("无法识别数据融合次数，结束任务")
                return
            self.info_set("Remaining Merge Count", merge_count)
            if merge_count == 0:
                self.log_info("未锁定声骸已耗尽，结束任务")
                return

            self.wait_click_ocr(match="批量融合", box="bottom_right", raise_if_not_found=True, settle_time=0.2,
                                after_sleep=0.5)
            confirm_box = self.box_of_screen(0.59, 0.59, 0.75, 0.66)
            self.wait_click_ocr(match="确认", box=confirm_box, raise_if_not_found=False, settle_time=0.2,
                                after_sleep=0.5)
            self.wait_ocr(match="获得声骸", box="top", raise_if_not_found=False, settle_time=1)
            self.info_incr("Merge Count", merge_count)
            self.click_relative(0.53, 0.05, after_sleep=0.5)

    def _read_merge_count(self):
        """
        Read the current merge count from the bottom-right text "数据融合次数：num".
        """
        result = self.ocr(box="bottom_right", match=re.compile(r"数据融合次数[:：]\s*\d+"))
        if not result:
            return None

        text = None
        if isinstance(result, list):
            text = result[0].name if result and hasattr(result[0], "name") else None
        elif hasattr(result, "name"):
            text = result.name
        if not text:
            return None

        match = re.search(r"数据融合次数[:：]\s*(\d+)", text)
        if not match:
            return None

        try:
            return int(match.group(1))
        except ValueError:
            return None
