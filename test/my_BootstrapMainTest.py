from __future__ import annotations

from ok import Logger, og
from auto import ensure_game_running
import time

logger = Logger.get_logger(__name__)


def main():
    """Minimal headless test: ensure game, stop it, ensure again."""
    from config import config as base_config
    from ok import OK

    cfg = dict(base_config)
    cfg["use_gui"] = False

    ok = OK(cfg)
    # Start executor so device manager/capture is initialized.
    ok.task_executor.start()

    start_timeout = cfg.get("start_timeout", 120)

    logger.info("Ensuring game window is ready (1st run)")
    ensure_game_running(ok, timeout=start_timeout)

    time.sleep(20)

    logger.info("Stopping game to trigger restart path")
    try:
        ok.device_manager.stop_hwnd()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to stop game during test", exc)

    time.sleep(5)

    logger.info("Ensuring game window is ready (2nd run)")
    ensure_game_running(ok, timeout=start_timeout)

    logger.info("Test completed; quitting OK")
    ok.quit()


if __name__ == "__main__":
    main()
