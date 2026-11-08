"""Helpers shared by the backup integration tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from floorpro import backup_file
from floorpro.services import backup_service


def only_backup(data_dir: Path, kind: str = "manual") -> Path:
    files = sorted((data_dir / "backups").glob(f"FloorPro-backup-*-{kind}*.fpbackup"))
    assert len(files) == 1, files
    return files[0]


def write_db_backup(
    folder: Path,
    db_bytes: bytes,
    *,
    schema_revision: str | None = None,
    name: str = "FloorPro-backup-2026-11-01-090000-manual.fpbackup",
    key: bytes | None = None,
    kdf: backup_file.KdfParams | None = None,
) -> Path:
    """Write arbitrary database bytes as a backup (default: with this computer's key)."""
    if key is None:
        stored = backup_service.load_key()
        key, kdf = stored.key, stored.kdf
    fields = {
        "kind": "manual",
        "created_at": datetime(2026, 11, 1, 9, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "app_version": "0.1.0",
        "schema_revision": schema_revision,
        "contents": {"customers": 0},
    }
    return backup_file.write_backup(folder, name, db_bytes, fields, key, kdf)


def sqlite_bytes(tmp: Path, *statements: str) -> bytes:
    path = tmp / "built.db"
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    try:
        for statement in statements:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()
    return path.read_bytes()


def tmp_is_empty(data_dir: Path) -> bool:
    folder = data_dir / "tmp"
    return not folder.exists() or list(folder.iterdir()) == []
