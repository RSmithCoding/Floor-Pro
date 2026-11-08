"""Restore from a listed backup (US2, FR-009 to FR-015, SC-003)."""

from __future__ import annotations

import time

from floorpro import backup_file
from floorpro.models import Customer
from floorpro.services import backup_service
from floorpro.templating import local_datetime_filter
from tests.conftest import db_dump, make_customer, page_text
from tests.integration.backup_helpers import only_backup, write_db_backup


def backed_up(client, session, data_dir):
    """Two customers, a manual backup, then changes made after it."""
    make_customer(session, first_name="Alice")
    make_customer(session, first_name="Bob")
    client.post("/backups")
    snapshot = db_dump(data_dir / "floorpro.db")
    path = only_backup(data_dir)
    bob = session.query(Customer).filter_by(first_name="Bob").one()
    session.delete(bob)
    make_customer(session, first_name="Carol")
    session.commit()
    return path, snapshot


def test_confirm_dialog(client, session, backup_password, data_dir):
    path, _ = backed_up(client, session, data_dir)
    response = client.get(f"/backups/local/{path.name}/restore")
    assert response.status_code == 200
    text = page_text(response)
    created = backup_service.read_info(path, "local").created_at
    assert local_datetime_filter(created) in text
    assert "Manual" in text
    assert "2 customers" in text
    assert (
        "Everything changed since then will be replaced. FloorPro will first save a Before "
        "restore backup of your current data." in text
    )
    assert (
        "Customers erased since this backup was made will come back and need erasing again." in text
    )
    assert 'name="confirm"' in text
    assert 'name="password"' not in text


def test_wrong_confirmation(client, session, backup_password, data_dir, htmx):
    path, _ = backed_up(client, session, data_dir)
    before = db_dump(data_dir / "floorpro.db")
    response = client.post(
        f"/backups/local/{path.name}/restore", data={"confirm": "restor"}, headers=htmx
    )
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#modal"
    assert "Type RESTORE to confirm." in page_text(response)
    assert db_dump(data_dir / "floorpro.db") == before


def test_restore(client, session, backup_password, data_dir, htmx):
    path, snapshot = backed_up(client, session, data_dir)
    pre_restore = db_dump(data_dir / "floorpro.db")
    response = client.post(
        f"/backups/local/{path.name}/restore", data={"confirm": " restore "}, headers=htmx
    )
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/"
    assert db_dump(data_dir / "floorpro.db") == snapshot

    created = backup_service.read_info(path, "local").created_at
    home = page_text(client.get("/"))
    assert f"Restored the backup from {local_datetime_filter(created)}" in home

    before_restore = only_backup(data_dir, "before-restore")
    copy = data_dir / "before.db"
    copy.write_bytes(backup_file.decrypt(before_restore, backup_service.load_key().key))
    assert db_dump(copy) == pre_restore


def test_restored_data_shows_without_restart(client, session, backup_password, data_dir):
    path, _ = backed_up(client, session, data_dir)
    client.post(f"/backups/local/{path.name}/restore", data={"confirm": "RESTORE"})
    text = page_text(client.get("/customers"))
    assert "Bob" in text
    assert "Carol" not in text


def test_restore_does_not_wait_on_its_own_requests(client, session, backup_password, data_dir):
    path, _ = backed_up(client, session, data_dir)
    session.close()
    client.get("/customers")
    client.get("/settings")
    started = time.monotonic()
    response = client.post(f"/backups/local/{path.name}/restore", data={"confirm": "RESTORE"})
    assert response.status_code == 200
    assert time.monotonic() - started < 2


def test_newer_version_is_refused(client, session, backup_password, data_dir):
    db = (data_dir / "floorpro.db").read_bytes()
    path = write_db_backup(data_dir / "backups", db, schema_revision="9999_from_the_future")
    before = db_dump(data_dir / "floorpro.db")
    text = page_text(client.get(f"/backups/local/{path.name}/restore"))
    assert "This backup was made by a newer version of FloorPro. Update FloorPro first." in text
    assert 'name="confirm"' not in text
    response = client.post(f"/backups/local/{path.name}/restore", data={"confirm": "RESTORE"})
    assert response.status_code == 422
    assert db_dump(data_dir / "floorpro.db") == before


def test_unprotected_legacy_copy_is_refused_here(client, backup_password, data_dir):
    import shutil

    legacy = data_dir / "backups" / "floorpro-20261101T090000000000Z-pre-0001.db"
    shutil.copyfile(data_dir / "floorpro.db", legacy)
    page = page_text(client.get("/backups"))
    assert "Not protected" in page
    assert f"/backups/local/{legacy.name}/restore" not in page  # no Restore action
    text = page_text(client.get(f"/backups/local/{legacy.name}/restore"))
    assert (
        "This older copy isn't protected. It can only be restored from the recovery screen." in text
    )
    assert 'name="confirm"' not in text
    response = client.post(f"/backups/local/{legacy.name}/restore", data={"confirm": "RESTORE"})
    assert response.status_code == 422
