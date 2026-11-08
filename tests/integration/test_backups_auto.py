"""Automatic daily backups and retention (US3, FR-017 to FR-019, SC-007)."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from floorpro import backup_file
from floorpro.app import create_app
from floorpro.domain.backups import BackupKind
from floorpro.services import backup_service
from tests.conftest import BACKUP_PASSWORD, page_text
from tests.integration.backup_helpers import write_db_backup

DAY1 = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch):
    state = {"now": DAY1}
    monkeypatch.setattr(backup_service, "now", lambda: state["now"])
    return state


def automatic(data_dir):
    return sorted((data_dir / "backups").glob("FloorPro-backup-*-automatic*.fpbackup"))


def start(data_dir, *, sync=True):
    app = create_app(data_dir)
    if sync:
        app.state.run_in_background = lambda fn: fn()
    else:
        app.state.run_in_background = lambda fn: threading.Thread(target=fn, daemon=True).start()
    return TestClient(app)


def test_one_automatic_backup_per_day(data_dir, clock):
    with start(data_dir):
        backup_service.set_password(BACKUP_PASSWORD)
    with start(data_dir):
        pass
    assert len(automatic(data_dir)) == 1
    today = DAY1.astimezone().date().isoformat()
    assert backup_service.load_prefs().last_auto_date == today
    assert backup_service.load_prefs().last_auto_ok is True

    with start(data_dir):  # same day again
        pass
    assert len(automatic(data_dir)) == 1

    clock["now"] = DAY1 + timedelta(days=1)
    with start(data_dir):
        pass
    assert len(automatic(data_dir)) == 2


def test_dashboard_triggers_when_left_open(
    client, sync_background, backup_password, data_dir, clock
):
    client.get("/")
    assert len(automatic(data_dir)) == 1
    client.get("/")
    assert len(automatic(data_dir)) == 1
    clock["now"] = DAY1 + timedelta(days=1)
    client.get("/")
    assert len(automatic(data_dir)) == 2


def test_setting_the_first_password_makes_the_first_backup(
    client, sync_background, data_dir, clock
):
    good = "a long enough password"
    client.post("/backups/password", data={"password": good, "password_confirm": good})
    assert len(automatic(data_dir)) == 1


def test_retention(client, sync_background, backup_password, data_dir, clock):
    folder = data_dir / "backups"
    counts = {"automatic": 15, "manual": 3, "before-restore": 2, "before-upgrade": 11}
    stored = backup_service.load_key()
    for slug, count in counts.items():
        for i in range(count):
            when = datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=i)
            name = f"FloorPro-backup-{when:%Y-%m-%d}-090000-{slug}.fpbackup"
            path = write_db_backup(folder, b"x", name=name, key=stored.key, kdf=stored.kdf)
            # give each file its own kind and time in the header
            _rewrite(path, slug.replace("-", "_"), when, stored)

    backup_service.run_automatic()

    kinds = {}
    for b in backup_service.list_backups():
        kinds[b.kind] = kinds.get(b.kind, 0) + 1
    assert kinds == {
        BackupKind.AUTOMATIC: 14,
        BackupKind.MANUAL: 3,
        BackupKind.BEFORE_RESTORE: 2,
        BackupKind.BEFORE_UPGRADE: 10,
    }
    names = [p.name for p in automatic(data_dir)]
    assert "FloorPro-backup-2026-10-01-090000-automatic.fpbackup" not in names
    assert "FloorPro-backup-2026-10-02-090000-automatic.fpbackup" not in names


def _rewrite(path, kind, when, stored):
    fields = {
        "kind": kind,
        "created_at": when.isoformat().replace("+00:00", "Z"),
        "app_version": "0.1.0",
        "schema_revision": None,
        "contents": {"customers": 0},
    }
    backup_file.write_backup(path.parent, path.name, b"x", fields, stored.key, stored.kdf)


def test_failure_is_recorded_and_shown(
    client, sync_background, backup_password, data_dir, clock, monkeypatch
):
    def broken(*_args, **_kwargs):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(backup_file, "write_backup", broken)
    backup_service.maybe_run_daily(client.app)
    prefs = backup_service.load_prefs()
    assert prefs.last_auto_ok is False
    assert prefs.last_auto_error == "The backup couldn't be saved."
    text = page_text(client.get("/"))
    assert "The last automatic backup failed: The backup couldn't be saved." in text


def test_switch_off_and_on(client, sync_background, backup_password, data_dir, clock, htmx):
    response = client.post("/backups/automatic", data={}, headers=htmx)
    assert "Automatic backups off" in page_text(response)
    assert backup_service.load_prefs().auto_enabled is False
    clock["now"] = DAY1 + timedelta(days=1)
    text = page_text(client.get("/"))
    assert automatic(data_dir) == []
    assert "Automatic backups are off." in text

    response = client.post("/backups/automatic", data={"auto_enabled": "on"}, headers=htmx)
    assert "Automatic backups on" in page_text(response)
    assert backup_service.load_prefs().auto_enabled is True


def test_startup_is_not_delayed(data_dir, monkeypatch):
    with start(data_dir):
        backup_service.set_password(BACKUP_PASSWORD)

    finished = threading.Event()
    real_snapshot = backup_service.snapshot

    def slow_snapshot(db_path):
        try:
            time.sleep(2)
            return real_snapshot(db_path)
        finally:
            finished.set()

    monkeypatch.setattr(backup_service, "snapshot", slow_snapshot)
    started = time.monotonic()
    with start(data_dir, sync=False) as client:
        elapsed = time.monotonic() - started
        assert client.get("/healthz").status_code == 200
    assert elapsed < 1
    assert finished.wait(10)
    with backup_service.acquire(timeout=10):  # let the background backup finish cleanly
        pass
