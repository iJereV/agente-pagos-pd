"""Typed accessors for environment variables."""

import os


class MissingSetting(RuntimeError):
    """Raised when a required environment variable is not set."""


def env_str(name: str, default: str | None = None) -> str:
    """Return the variable, the default, or raise when neither exists."""
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise MissingSetting(f"environment variable {name} is required")
    return value


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw in (None, "") else int(raw)


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw in (None, "") else float(raw)
