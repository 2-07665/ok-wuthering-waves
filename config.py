import os
from pathlib import Path

from ok import ConfigOption
from src.task.process_feature import process_feature

version = "my"

GAME_EXE_PATH = Path(r"D:\Games\Wuthering Waves\Wuthering Waves Game\Wuthering Waves.exe")
#GAME_EXE_PATH = Path(r"D:\Program\Wuthering Waves\Wuthering Waves Game\Wuthering Waves.exe")

def calculate_pc_exe_path(running_path):
    # We bypass auto-detection and return the known game executable path.
    return str(GAME_EXE_PATH)

key_config_option = ConfigOption('Game Hotkey Config', {
    'Echo Key': 'q',
    'Liberation Key': 'r',
    'Resonance Key': 'e',
    'Tool Key': 't',
}, description='In Game Hotkey for Skills')

char_config_option = ConfigOption('Character Config', {
    'Iuno C6': False,
}, description='Character Config')

pick_echo_config_option = ConfigOption('Pick Echo Config', {
    'Use OCR': False
}, config_description={
    'Use OCR': 'Turn on if your CPU is Powerful for more accuracy'}, description='Turn on to enable auto pick echo')

monthly_card_config_option = ConfigOption('Monthly Card Config', {
    'Check Monthly Card': False,
    'Monthly Card Time': 16
}, description='Turn on to avoid interruption by monthly card when executing tasks', config_description={
    'Check Monthly Card': 'Check for monthly card to avoid interruption of tasks',
    'Monthly Card Time': 'Your computer\'s local time when the monthly card will popup, hour in (1-24)'
})

config = {
    'debug': False,  # Optional, default: False
    'use_gui': True,
    'config_folder': 'configs',
    'gui_icon': 'icon.png',
    'global_configs': [key_config_option, char_config_option, pick_echo_config_option, monthly_card_config_option],
    'ocr': {
        'lib': 'onnxocr',
        'params': {
            'use_openvino': True,
        }
    },
    'my_app': ['src.globals', 'Globals'],
    'start_timeout': 120,  # default 60
    'login_timeout': 180,
    'wait_until_settle_time': 0,
    # required if using feature detection
    'template_matching': {
        'coco_feature_json': os.path.join('assets', 'result.json'),
        'default_horizontal_variance': 0.002,
        'default_vertical_variance': 0.002,
        'default_threshold': 0.8,
        'feature_processor': process_feature,
    },
    'windows': {  # required  when supporting windows game
        'exe': 'Client-Win64-Shipping.exe',
        'calculate_pc_exe_path': calculate_pc_exe_path,
        'hwnd_class': 'UnrealWindow',
        'interaction': 'PostMessage',
        'capture_method': ['WGC', 'BitBlt_RenderFull'],  # Windows版本支持的话, 优先使用WGC, 否则使用BitBlt_Full
        'check_hdr': False,
        'force_no_hdr': False,
        'check_night_light': True,
        'force_no_night_light': False,
    },
    'window_size': {
        'width': 900,
        'height': 600,
        'min_width': 900,
        'min_height': 600,
    },
    'supported_resolution': {
        'ratio': '16:9',
        'min_size': (1280, 720),
        'resize_to': [(2560, 1440), (1920, 1080), (1600, 900), (1280, 720)],
    },
    'screenshots_folder': "screenshots",
    'gui_title': 'OK-WW',  # Optional
    # 'coco_feature_folder': get_path(__file__, 'assets/coco_feature'),  # required if using feature detection
    'log_file': 'logs/ok-ww.log',  # Optional, auto rotating every day
    'error_log_file': 'logs/ok-ww_error.log',
    'launcher_log_file': 'logs/launcher.log',
    'launcher_error_log_file': 'logs/launcher_error.log',
    'version': version,
    'onetime_tasks': [  # tasks to execute
        ["custom.task.my_LoginTask", "LoginTask"],
        ["src.task.DailyTask", "DailyTask"],
        ["src.task.TacetTask", "TacetTask"],
        ["src.task.NightmareNestTask", "NightmareNestTask"],
        ["custom.task.my_FastFarmEchoTask", "FastFarmEchoTask"],
    ], 'trigger_tasks': [
        ["src.task.MouseResetTask", "MouseResetTask"],
    ], 'scene': ["src.scene.WWScene", "WWScene"],
}
