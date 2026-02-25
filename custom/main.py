import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if __name__ == '__main__':
    from config import config
    from ok import OK
    from custom.src.patches import apply_all_patches

    apply_all_patches()
    ok = OK(config)
    ok.start()
