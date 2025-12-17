import os
from pathlib import Path

from dotenv import load_dotenv


# Assume .env lives in the project root (one level up from this file)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


# Load .env once at import time
load_dotenv(dotenv_path=ENV_PATH)


def env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    """
    Read an environment variable.
    - If `required=True` and the variable is missing (and no default is given), raises RuntimeError.
    - Otherwise returns the value or `default` (which is None by default).
    """
    value = os.getenv(name, default)
    if required and value is None:
        raise RuntimeError(f"Environment variable '{name}' is required but missing.")
    return value
