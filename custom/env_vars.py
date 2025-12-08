from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
_DOTENV_LOADED = False


def load_dotenv(path: str | Path | None = None) -> None:
    """Load environment variables from a .env file without overriding existing ones."""
    env_path = Path(path or _DEFAULT_ENV_PATH)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _ensure_loaded() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    load_dotenv()
    _DOTENV_LOADED = True


def env_var(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    """
    Read an environment variable after ensuring .env has been loaded.
    If required=True, raises RuntimeError when missing.
    """
    _ensure_loaded()
    value = os.environ.get(name, default)
    if required and value is None:
        raise RuntimeError(f"Environment variable '{name}' is required but missing.")
    return value
