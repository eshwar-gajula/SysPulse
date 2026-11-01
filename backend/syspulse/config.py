"""Bounded runtime configuration and private data-directory selection."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _bounded_number(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number between {minimum:g} and {maximum:g}.") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return value


def default_data_directory() -> Path:
    configured = os.environ.get("SYSPULSE_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "SysPulse"


@dataclass(frozen=True, slots=True)
class Settings:
    data_directory: Path
    sample_interval_seconds: float = 2.0
    retention_hours: int = 24

    @property
    def database_path(self) -> Path:
        return self.data_directory / "syspulse.sqlite3"


def load_settings() -> Settings:
    interval = _bounded_number("SYSPULSE_SAMPLE_INTERVAL", 2.0, 1.0, 60.0)
    retention = _bounded_number("SYSPULSE_RETENTION_HOURS", 24.0, 1.0, 168.0)
    if not retention.is_integer():
        raise ValueError("SYSPULSE_RETENTION_HOURS must be a whole number from 1 to 168.")
    return Settings(
        data_directory=default_data_directory(),
        sample_interval_seconds=interval,
        retention_hours=int(retention),
    )
