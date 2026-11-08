"""The backups list across both locations (FR-007, FR-008)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from floorpro import backup_file
from floorpro.services import backup_service
from tests.conftest import page_text


def write(folder, name, kind, created, stored):
    fields = {
        "kind": kind,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "app_version": "0.1.0",
        "schema_revision": None,
        "contents": {"customers": 7},
    }
    return backup_file.write_backup(folder, name, b"x", fields, stored.key, stored.kdf)


def rows(text):
    body = text.split("<tbody", 1)[1].split("</tbody>", 1)[0]
    return body.split("</tr>")[:-1]


def test_list_labels_and_order(client, backup_password, data_dir, tmp_path):
    stored = backup_service.load_key()
    local = data_dir / "backups"
    folder = tmp_path / "usb"
    folder.mkdir()
    backup_service.update_prefs(folder=str(folder))
    base = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    write(
        local,
        "FloorPro-backup-2026-11-01-090000-before-upgrade.fpbackup",
        "before_upgrade",
        base,
        stored,
    )
    write(
        folder,
        "FloorPro-backup-2026-11-03-090000-automatic.fpbackup",
        "automatic",
        base + timedelta(days=2),
        stored,
    )
    legacy = local / "floorpro-20261102T090000000000Z-pre-0001.db"
    with sqlite3.connect(legacy) as conn:
        conn.execute("CREATE TABLE customer (id INTEGER)")
    (local / "FloorPro-backup-2026-10-01-090000-manual.fpbackup").write_bytes(b"garbage" * 10)
    (local / "notes.txt").write_text("not listed")

    text = page_text(client.get("/backups"))
    listed = rows(text)
    assert len(listed) == 4
    assert "Automatic" in listed[0] and "usb" in listed[0]
    assert "Before upgrade" in listed[1] and "Not protected" in listed[1]
    assert "Before upgrade" in listed[2] and "Not protected" not in listed[2]
    assert "Damaged or not a FloorPro backup" in listed[3]
    assert "notes.txt" not in text


def test_paths_outside_a_location_are_not_reachable(client, backup_password, data_dir):
    (data_dir / "evil.fpbackup").write_bytes(b"x")
    assert client.get("/backups/local/..%2Fevil.fpbackup/restore").status_code == 404
    assert client.get("/backups/local/evil.fpbackup/restore").status_code == 404
    assert client.get("/backups/elsewhere/x.fpbackup/restore").status_code == 404
