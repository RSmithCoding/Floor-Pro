"""Run database migrations at startup, backing the database up first (Principle I)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from floorpro.db import make_engine
from floorpro.paths import backups_dir, resource_path

log = logging.getLogger(__name__)

KEEP_BACKUPS = 10
BACKUP_GLOB = "floorpro-*-pre-*.db"


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(resource_path("migrations")))
    return cfg


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


def current_revision(db_path: Path) -> str | None:
    if not db_path.exists():
        return None
    engine = make_engine(db_path)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


def backup_if_needed(db_path: Path) -> Path | None:
    """Back up an existing, out-of-date database before migrating (Principle I).

    Once a backup password is set this is a protected ``.fpbackup`` (kind ``before_upgrade``);
    before that, a plain copy as in feature 001.
    """
    if not db_path.exists() or current_revision(db_path) == head_revision():
        return None
    from floorpro.services import backup_service  # avoids a circular import

    if backup_service.key_is_set():
        return backup_service.write_before_upgrade(db_path)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = backups_dir() / f"floorpro-{stamp}-pre-{head_revision()}.db"
    with sqlite3.connect(db_path) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    log.info("Backed up database to %s before migrating", target.name)
    _prune_backups()
    return target


def _prune_backups() -> None:
    backups = sorted(backups_dir().glob(BACKUP_GLOB), key=lambda p: p.name, reverse=True)
    for old in backups[KEEP_BACKUPS:]:
        old.unlink()


def upgrade_to_head(db_path: Path, backup: bool = True) -> None:
    """Migrate to head. Staged restores pass ``backup=False``: the backup file is the original."""
    if backup:
        backup_if_needed(db_path)
    engine = make_engine(db_path)
    try:
        with engine.begin() as conn:
            cfg = alembic_config()
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
    finally:
        engine.dispose()
