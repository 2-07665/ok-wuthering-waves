from __future__ import annotations

import sys
import time

from ok import OK, Logger
from config import config as base_config

logger = Logger.get_logger(__name__)

# Hardcoded test parameters; edit these to try different targets.
MATCH_TEXT = "数据坞"          # string or regex pattern
BOX_NAME = "right"            # named box (e.g. right/top_left) or None for full frame
CLICK = True                  # set False to only log results
TIMEOUT_SEC = 20
TARGET_HEIGHT = 720           # 0 to disable downscale before OCR
OCR_LIB = "default"           # key from config['ocr']


def ensure_capture_ready(ok: OK, timeout: int) -> None:
    """Wait until capture/interaction are connected to the game."""
    dm = ok.device_manager
    end = time.time() + timeout
    while time.time() < end:
        dm.do_refresh(True)
        preferred = dm.get_preferred_device()
        capture_ready = (
            preferred
            and preferred.get("connected")
            and dm.capture_method is not None
            and dm.capture_method.connected()
        )
        interaction_ready = dm.interaction is not None
        if capture_ready and interaction_ready:
            return
        time.sleep(2)
    raise RuntimeError("Game window not ready within timeout.")


def main() -> int:
    cfg = dict(base_config)
    cfg["use_gui"] = False
    cfg["debug"] = True

    ok = OK(cfg)
    executor = ok.task_executor
    executor.start()
    ensure_capture_ready(ok, cfg.get("start_timeout", 120))

    box = BOX_NAME or None
    logger.info(f"Waiting for OCR match={MATCH_TEXT!r} box={box or 'full-frame'} click={CLICK}")
    try:
        if CLICK:
            hit = executor.wait_click_ocr(
                match=MATCH_TEXT,
                box=box,
                time_out=TIMEOUT_SEC,
                target_height=TARGET_HEIGHT,
                raise_if_not_found=True,
                settle_time=0.2,
                log=True,
                lib=OCR_LIB,
            )
            logger.info(f"Clicked {hit}")
        else:
            hits = executor.wait_ocr(
                match=MATCH_TEXT,
                box=box,
                time_out=TIMEOUT_SEC,
                target_height=TARGET_HEIGHT,
                log=True,
                lib=OCR_LIB,
            )
            if hits:
                for h in hits:
                    logger.info(f"OCR hit: {h}")
            else:
                logger.warning("No OCR match found.")
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("OCR playground failed", exc)
        return 1
    finally:
        ok.quit()


if __name__ == "__main__":
    main()
