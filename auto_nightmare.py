from custom.ok_wrap import start_ok_and_game, run_onetime_task
from src.task.NightmareNestTask import NightmareNestTask


ok = start_ok_and_game()
nightmare_nest_task = ok.task_executor.get_task_by_class(NightmareNestTask)
run_onetime_task(ok.task_executor, nightmare_nest_task)
ok.quit()
