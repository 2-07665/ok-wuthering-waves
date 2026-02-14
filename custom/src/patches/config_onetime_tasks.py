from config import config


CUSTOM_ONETIME_TASKS = (
    ("custom.src.task.my_FastFarmEchoTask", "FastFarmEchoTask"),
    ("custom.src.task.my_FiveToOneTask", "FiveToOneTask"),
    ("custom.src.task.my_StaminaTask", "StaminaTask"),
)


def patch_config_onetime_tasks() -> None:
    if config.get("_my_patch_onetime_tasks_applied"):
        return

    onetime_tasks = config.get("onetime_tasks")

    existing = {tuple(item) for item in onetime_tasks if isinstance(item, (list, tuple)) and len(item) == 2}

    for module_name, class_name in CUSTOM_ONETIME_TASKS:
        item = (module_name, class_name)
        if item not in existing:
            onetime_tasks.append([module_name, class_name])
            existing.add(item)

    config["_my_patch_onetime_tasks_applied"] = True
