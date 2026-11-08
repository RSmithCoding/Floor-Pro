"""Filesystem locations for FloorPro.

``resource_path`` finds files shipped inside the package (templates, static files,
migrations) both in development and inside a PyInstaller build. ``data_dir`` is where the
shop's own data lives: the per-user application-data directory, never beside the executable.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

import platformdirs

APP_NAME = "FloorPro"
DATA_DIR_ENV = "FLOORPRO_DATA_DIR"


def package_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "floorpro"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def resource_path(relative: str) -> Path:
    """Path to a resource bundled with the package, e.g. ``resource_path("templates")``."""
    return package_root() / relative


def data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    path = (
        Path(override) if override else Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "floorpro.db"


def backups_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def secret_key() -> bytes:
    """Per-install signing key, created on first use."""
    path = data_dir() / "secret.key"
    if path.exists():
        key = path.read_bytes()
        if len(key) >= 32:
            return key
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    return key
