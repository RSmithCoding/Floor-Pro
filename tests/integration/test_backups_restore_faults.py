"""Restores that fail leave current data exactly as it was (SC-004, FR-011 to FR-013)."""

from __future__ import annotations

import sqlite3

import pytest

from floorpro.services import backup_service
from tests.conftest import db_dump, make_customer, page_text
from tests.integration.backup_helpers import (
    only_backup,
    sqlite_bytes,
    tmp_is_empty,
    write_db_backup,
)

DAMAGED = "This backup is damaged and can't be used. Your current data hasn't been changed."


@pytest.fixture
def setup(client, session, backup_password, data_dir):
    make_customer(session, first_name="Alice")
    client.post("/backups")
    make_customer(session, first_name="Bob")
    return only_backup(data_dir)


def restore(client, path, loc="local"):
    return client.post(f"/backups/{loc}/{path.name}/restore", data={"confirm": "RESTORE"})


def assert_unchanged(data_dir, before):
    assert db_dump(data_dir / "floorpro.db") == before
    assert tmp_is_empty(data_dir)


def test_flipped_payload_byte(client, setup, data_dir):
    before = db_dump(data_dir / "floorpro.db")
    data = bytearray(setup.read_bytes())
    data[-40] ^= 0xFF
    setup.write_bytes(bytes(data))
    response = restore(client, setup)
    assert response.status_code == 422
    assert DAMAGED in page_text(response)
    assert_unchanged(data_dir, before)


def test_truncated_file(client, setup, data_dir):
    before = db_dump(data_dir / "floorpro.db")
    setup.write_bytes(setup.read_bytes()[:-500])
    response = restore(client, setup)
    assert response.status_code == 422
    assert DAMAGED in page_text(response)
    assert_unchanged(data_dir, before)


def test_before_restore_backup_fails(client, setup, data_dir, monkeypatch):
    before = db_dump(data_dir / "floorpro.db")

    def fail(*_args, **_kwargs):
        raise backup_service.BackupFailed("There isn't enough space to save the backup.")

    def must_not_swap(*_args, **_kwargs):
        raise AssertionError("swap attempted")

    monkeypatch.setattr(backup_service, "make_backup", fail)
    monkeypatch.setattr(backup_service, "swap_in", must_not_swap)
    response = restore(client, setup)
    assert response.status_code == 422
    text = page_text(response)
    assert "couldn't save a Before restore backup" in text
    assert "There isn't enough space to save the backup." in text
    assert_unchanged(data_dir, before)


def test_swap_fails(client, setup, data_dir, monkeypatch):
    before = db_dump(data_dir / "floorpro.db")

    def boom(_staged, _live):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(backup_service, "copy_database", boom)
    response = restore(client, setup)
    assert response.status_code == 422
    assert "The restore couldn't be completed." in page_text(response)
    assert db_dump(data_dir / "floorpro.db") == before


def test_decrypted_database_fails_integrity_check(client, setup, data_dir, tmp_path):
    before = db_dump(data_dir / "floorpro.db")
    rows = ", ".join(f"('{'x' * 500}')" for _ in range(200))
    good = bytearray(
        sqlite_bytes(
            tmp_path,
            "CREATE TABLE alembic_version (version_num TEXT)",
            "CREATE TABLE business_settings (id INTEGER)",
            "CREATE TABLE filler (value TEXT)",
            f"INSERT INTO filler VALUES {rows}",
        )
    )
    for offset in range(4096 * 3, 4096 * 3 + 2000):
        good[offset] = 0xAB
    path = write_db_backup(data_dir / "backups", bytes(good))
    response = restore(client, path)
    assert response.status_code == 422
    assert DAMAGED in page_text(response)
    assert_unchanged(data_dir, before)


def test_decrypted_database_missing_tables(client, setup, data_dir, tmp_path):
    before = db_dump(data_dir / "floorpro.db")
    from floorpro.migrate import head_revision

    db = sqlite_bytes(
        tmp_path,
        "CREATE TABLE alembic_version (version_num TEXT)",
        f"INSERT INTO alembic_version VALUES ('{head_revision()}')",
    )
    path = write_db_backup(data_dir / "backups", db)
    response = restore(client, path)
    assert response.status_code == 422
    assert DAMAGED in page_text(response)
    assert_unchanged(data_dir, before)


def test_unreachable_folder_does_not_block_a_restore(client, setup, data_dir, tmp_path):
    backup_service.update_prefs(folder=str(tmp_path / "unplugged-usb"))
    response = restore(client, setup)
    assert response.status_code == 200
    assert only_backup(data_dir, "before-restore").parent == data_dir / "backups"
    assert tmp_is_empty(data_dir)
