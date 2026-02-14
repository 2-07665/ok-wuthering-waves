import os
from pathlib import Path
from typing import Literal, overload

from dotenv import load_dotenv


ENV_FOLDER = Path(__file__).resolve().parent.parent / "env"
PROJECT_ROOT = ENV_FOLDER.parents[2]
ENV_FILE_ENV = "ENV_FILE"
DEFAULT_ENV_PATH = ENV_FOLDER / ".env"

_DOTENV_LOADED = False

def _ensure_dotenv_loaded() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    env_file = os.getenv(ENV_FILE_ENV)
    if env_file:
        normalized = env_file.replace("\\", "/")
        raw_path = Path(normalized)
        if raw_path.is_absolute():
            env_path = raw_path
        else:
            candidates = [
                Path.cwd() / raw_path,
                PROJECT_ROOT / raw_path,
                ENV_FOLDER / raw_path,
            ]
            if raw_path.parent == Path("."):
                candidates.insert(0, ENV_FOLDER / raw_path.name)
            env_path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    else:
        env_path = DEFAULT_ENV_PATH
    load_dotenv(dotenv_path=env_path)
    _DOTENV_LOADED = True


@overload
def env(name: str, default: str | None = None, *, required: Literal[True]) -> str: ...

@overload
def env(name: str, default: str, *, required: bool = False) -> str: ...

@overload
def env(name: str, default: str | None = None, *, required: Literal[False] = False) -> str | None: ...


def env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    _ensure_dotenv_loaded()
    value = os.getenv(name, default)
    if required and value is None:
        raise RuntimeError(f"Environment variable '{name}' is required but missing.")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable with a default."""
    raw = env(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    return normalized in {"true", "1", "yes", "y", "是", "on"}
