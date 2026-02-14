from custom.src.ok_wrap import start_ok_and_game, run_onetime_task
from src.task.NightmareNestTask import NightmareNestTask

ok = start_ok_and_game()
task = ok.task_executor.get_task_by_class(NightmareNestTask)
run_onetime_task(ok.task_executor, task)
ok.quit()
