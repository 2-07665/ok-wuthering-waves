import os
from pathlib import Path

from dotenv import load_dotenv


# Assume .env lives in the project root (one level up from this file)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

_DOTENV_LOADED = False


def _ensure_dotenv_loaded() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    load_dotenv(dotenv_path=ENV_PATH)
    _DOTENV_LOADED = True


def env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    """
    Read an environment variable.
    - If `required=True` and the variable is missing (and no default is given), raises RuntimeError.
    - Otherwise returns the value or `default` (which is None by default).
    """
    _ensure_dotenv_loaded()
    value = os.getenv(name, default)
    if required and value is None:
        raise RuntimeError(f"Environment variable '{name}' is required but missing.")
    return value


def required_env(name: str) -> str:
    """Read a required environment variable and return the value."""
    value = env(name, required=True)
    assert value is not None
    return value


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable with a default."""
    raw = env(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    return normalized in {"true", "1", "yes", "y", "是", "on"}
