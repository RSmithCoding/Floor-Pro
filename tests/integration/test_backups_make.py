"""Back up now (US1, FR-002 to FR-006, SC-008)."""

from __future__ import annotations

import errno
import re
import sqlite3
from datetime import UTC, datetime

from floorpro import backup_file
from floorpro.migrate import head_revision
from floorpro.models import Customer
from floorpro.services import backup_service
from floorpro.templating import filesize_filter
from tests.conftest import db_dump, make_customer, page_text

NAME_RE = r"^FloorPro-backup-\d{4}-\d{2}-\d{2}-\d{6}-manual(-\d+)?\.fpbackup$"


def backup_files(data_dir):
    return sorted((data_dir / "backups").glob("*.fpbackup"))


def decrypted_copy(path, data_dir):
    copy = data_dir / "decrypted.db"
    copy.write_bytes(backup_file.decrypt(path, backup_service.load_key().key))
    return copy


def test_back_up_now(client, session, backup_password, data_dir):
    make_customer(session)
    make_customer(session, first_name="Ann")
    response = client.post("/backups")
    assert response.status_code == 200
    text = page_text(response)
    assert "Backup made · 2 customers" in text

    files = backup_files(data_dir)
    assert len(files) == 1
    assert re.match(NAME_RE, files[0].name)
    header = backup_file.read_header(files[0])
    assert header["kind"] == "manual"
    assert header["contents"]["customers"] == 2
    assert header["schema_revision"] == head_revision()

    first_row = text.split("<tbody", 1)[1].split("</tr>", 1)[0]
    assert "Manual" in first_row
    assert filesize_filter(files[0].stat().st_size) in first_row
    assert "This computer" in first_row
    assert ">2<" in first_row.replace(" ", "")


def test_backup_contents_are_exact(client, session, backup_password, data_dir):
    make_customer(session)
    client.post("/backups")
    copy = decrypted_copy(backup_files(data_dir)[0], data_dir)
    assert db_dump(copy) == db_dump(data_dir / "floorpro.db")


def test_htmx_back_up_now_pushes_the_url(client, backup_password, htmx):
    response = client.post("/backups", headers=htmx)
    assert response.headers["HX-Push-Url"] == "/backups"
    assert "Backup made · 0 customers" in page_text(response)


def test_no_password(client, data_dir):
    response = client.post("/backups")
    assert response.status_code == 200
    assert "Set a backup password first." in page_text(response)
    assert backup_files(data_dir) == []


def test_disk_full(client, backup_password, data_dir, monkeypatch):
    def full(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(backup_file, "write_backup", full)
    response = client.post("/backups")
    assert response.status_code == 200
    assert "There isn't enough space to save the backup." in page_text(response)
    assert list((data_dir / "backups").glob("*.fpbackup")) == []
    assert list((data_dir / "backups").glob("*.partial")) == []
    assert backup_service.load_prefs().last_success_at is None
    assert list((data_dir / "tmp").iterdir()) == []


def test_snapshot_is_consistent_during_a_write(client, app, session, backup_password, data_dir):
    make_customer(session)
    writer = app.state.sessionmaker()
    try:
        writer.add(
            Customer(
                customer_type="domestic",
                show_vat_breakdown=False,
                first_name="Uncommitted",
                last_name="Row",
                mobile_phone="07700 900111",
                mobile_phone_digits="07700900111",
                marketing_consent=False,
                is_archived=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        writer.flush()  # the write transaction is open, not committed
        response = client.post("/backups")
        assert "Backup made · 1 customer" in page_text(response)
    finally:
        writer.rollback()
        writer.close()
    copy = decrypted_copy(backup_files(data_dir)[0], data_dir)
    with sqlite3.connect(copy) as conn:
        names = [row[0] for row in conn.execute("SELECT first_name FROM customer")]
    assert names == ["Jane"]


def test_backup_file_contains_no_personal_details(client, session, backup_password, data_dir):
    make_customer(
        session,
        first_name="Zebedee",
        last_name="Quixotic",
        email="zebedee.quixotic@example.com",
        mobile_phone="07700 900987",
        address_line1="17 Marmalade Mews",
        postcode="SW1A 1AA",
    )
    client.post("/backups")
    raw = backup_files(data_dir)[0].read_bytes()
    for secret in (
        "Zebedee",
        "Quixotic",
        "zebedee.quixotic@example.com",
        "07700900987",
        "07700 900987",
        "Marmalade Mews",
        "SW1A 1AA",
    ):
        assert secret.encode("utf-8") not in raw
        assert secret.encode("utf-16-le") not in raw


def test_busy(client, backup_password, data_dir, monkeypatch):
    monkeypatch.setattr(backup_service, "LOCK_TIMEOUT", 0.1)
    assert backup_service.LOCK.acquire(timeout=1)
    try:
        response = client.post("/backups")
    finally:
        backup_service.LOCK.release()
    assert "A backup is already in progress. Try again in a moment." in page_text(response)
    assert backup_files(data_dir) == []
