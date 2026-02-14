from ok import Logger
from src.task.BaseWWTask import BaseWWTask

logger = Logger.get_logger(__name__)


def use_stamina(self, once, must_use=0, prefer_single=False):
    self.sleep(1)
    current, back_up, total = self.get_stamina()
    y = 0.62
    if prefer_single:
        x = 0.32
        used = once
        logger.info("设置使用单倍体力")
    elif current >= once * 2:
        used = once * 2
        x = 0.67
        logger.info(f"当前体力大于等于双倍, {current} >= {once * 2}")
    elif must_use > once and total >= once * 2:
        used = once * 2
        x = 0.67
        logger.info(f"当前加备用大于日常剩余所需, 使用双倍, {must_use} >= {once} and {total} >= {once * 2}")
    else:
        logger.info("使用单倍体力")
        used = once
        x = 0.32
    self.click(x, y, after_sleep=0.5)
    if self.wait_feature('gem_add_stamina', horizontal_variance=0.4, vertical_variance=0.05,
                         time_out=1):  # 看是否需要使用备用体力
        self.click(0.70, 0.71, after_sleep=0.5)  # 点击确认
        self.click(0.70, 0.71, after_sleep=1)
        self.back(after_sleep=0.5)
        self.click(x, y, after_sleep=0.5)

    current -= used
    must_use -= used
    total -= used
    if total < once:
        logger.info(f"current stamina: {current} not enough to continue")
        can_continue = False
    elif must_use <= 0 and current < once:
        can_continue = False
        logger.info(f"current stamina: {current} must_use completed, no need to use back_up")
    else:
        can_continue = True
    return can_continue, used


def patch_basewwtask_use_stamina() -> None:
    if getattr(BaseWWTask, "_my_patch_use_stamina", False):
        return
    BaseWWTask._my_patch_use_stamina = True
    BaseWWTask._my_patch_use_stamina_original = BaseWWTask.use_stamina
    BaseWWTask.use_stamina = use_stamina
