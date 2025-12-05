from __future__ import annotations

import re
from pathlib import Path
import sys

import cv2

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ok import ExitEvent, GlobalConfig, TaskExecutor
from config import config as base_config
from custom.task.my_LoginTask import LoginTask


class DummyDeviceManager:
    """Minimal device manager stub for offline OCR probing."""

    def __init__(self):
        self.capture_method = None
        self.interaction = None
        self.hwnd_window = None
        self.device = None
        self.exit_event = None


def build_executor(frame):
    cfg = dict(base_config)
    cfg["use_gui"] = False
    cfg["ocr"] = dict(cfg.get("ocr", {}))
    if "default" not in cfg["ocr"]:
        cfg["ocr"]["default"] = cfg["ocr"]
    global_config = GlobalConfig(cfg.get("global_configs"))

    dm = DummyDeviceManager()
    exit_event = ExitEvent()
    dm.exit_event = exit_event
    executor = TaskExecutor(
        dm,
        exit_event=exit_event,
        feature_set=None,
        config_folder=cfg.get("config_folder"),
        debug=cfg.get("debug", False),
        global_config=global_config,
        ocr_target_height=cfg.get("ocr", {}).get("target_height", 0),
        config=cfg,
    )
    executor.paused = False
    executor.debug_mode = True
    executor._frame = frame
    return executor


def print_results(label, boxes):
    print(f"\n[{label}] found {len(boxes) if boxes else 0} matches")
    if not boxes:
        return
    for b in boxes:
        print(f"  text={b.name!r} conf={b.confidence:.3f} box=({b.x},{b.y},{b.width},{b.height})")


def main():
    img_path = Path("test/update_complete.png")
    frame = cv2.imread(str(img_path))
    if frame is None:
        raise SystemExit(f"Failed to load screenshot: {img_path}")

    executor = build_executor(frame)
    task = LoginTask(executor=executor)

    # Probe both the notice text and the confirm button area with the current OCR stack.
    probes = [
        (
            "notice_center",
            dict(
                x=0.15,
                y=0.25,
                to_x=0.85,
                to_y=0.75,
                match=[re.compile("更新完成"), re.compile("重启")],
                frame=frame,
                log=False,
            ),
        ),
        (
            "confirm_tight",
            dict(
                x=0.55,
                y=0.58,
                to_x=0.78,
                to_y=0.72,
                match="确认",
                frame=frame,
                log=False,
            ),
        ),
        (
            "confirm_wide_fallback",
            dict(
                x=0.45,
                y=0.55,
                to_x=0.8,
                to_y=0.78,
                match="确认",
                frame=frame,
                log=False,
            ),
        ),
    ]

    for label, params in probes:
        boxes = task.ocr(**params)
        print_results(label, boxes)


if __name__ == "__main__":
    main()
