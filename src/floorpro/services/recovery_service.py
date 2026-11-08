"""Startup recovery: detect an unreadable database, move it aside, restore or start fresh.

Damaged files are moved into ``damaged/`` and never deleted (research.md §13).
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from floorpro import paths
from floorpro.services import backup_service

log = logging.getLogger(__name__)

REASON = "FloorPro couldn't open your shop's data. It may have been damaged."


@dataclass(frozen=True)
class RecoveryInfo:
    reason: str
    detail: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def recovery_for(exc: BaseException) -> RecoveryInfo:
    detail = f"{type(exc).__name__}: {exc}"
    log.error("Entering recovery mode: %s", detail)
    return RecoveryInfo(REASON, detail)


def check_database(db_path: Path) -> RecoveryInfo | None:
    """None if the database is missing (a new install) or opens and passes quick_check."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            result = conn.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return recovery_for(exc)
    if result != "ok":
        return recovery_for(sqlite3.DatabaseError(f"quick_check: {result}"))
    return None


def move_aside(db_path: Path) -> Path:
    """Move the database and its -wal/-shm files into damaged/. Returns the new main path."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = paths.damaged_dir() / f"floorpro-{stamp}.db"
    for suffix in ("", "-wal", "-shm"):
        source = Path(f"{db_path}{suffix}")
        if source.exists():
            shutil.move(source, Path(f"{target}{suffix}"))
    log.warning("Moved the unreadable database aside to %s", target.name)
    return target


def restore_in_recovery(path: Path, password: str | None = None) -> None:
    """Stage and check the backup first; only then move the damaged files and put it in place.

    No Before restore backup: the data can't be read, and the moved-aside file keeps it.
    """
    db_path = paths.db_path()
    backup_service.open_backup(path)
    with backup_service.acquire():
        staged = backup_service.stage(path, password)
        try:
            move_aside(db_path)
            backup_service.copy_database(staged, db_path)
        finally:
            backup_service.remove_db_files(staged)
    log.info("Restored backup %s in recovery mode", path.name)


def start_fresh() -> Path:
    """Move the damaged files aside and create an empty database."""
    from floorpro.migrate import upgrade_to_head

    moved = move_aside(paths.db_path())
    upgrade_to_head(paths.db_path())
    return moved
