from ok import Logger
logger = Logger.get_logger(__name__)

from .config_onetime_tasks import patch_config_onetime_tasks
from .use_stamina import patch_basewwtask_use_stamina
from .wait_login import patch_basewwtask_wait_login_disable_restart

PATCH_REGISTRY = {
    "config_onetime_tasks": patch_config_onetime_tasks,
    "basewwtask_use_stamina": patch_basewwtask_use_stamina,
    "basewwtask_wait_login_disable_restart": patch_basewwtask_wait_login_disable_restart,
}

DEFAULT_PATCHES = tuple(PATCH_REGISTRY.keys())

_patches_applied = False


def apply_all_patches(enabled: tuple[str, ...] | list[str] | None = None) -> None:
    global _patches_applied
    if _patches_applied:
        return

    patch_names = tuple(enabled) if enabled is not None else DEFAULT_PATCHES
    for name in patch_names:
        patch_func = PATCH_REGISTRY.get(name)
        if patch_func is None:
            raise ValueError(f"Unknown patch: {name}")
        patch_func()
        logger.info(f"MY-OK-WW: Applied patch {name}")
    _patches_applied = True
