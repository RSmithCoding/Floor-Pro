"""The dashboard backup card (FR-020)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from floorpro.services import backup_service
from tests.conftest import page_text
from tests.integration.backup_helpers import write_db_backup


def card(client):
    text = page_text(client.get("/"))
    return text.split('id="backup-card"', 1)[1].split("</section>", 1)[0]


def healthy(**changes):
    values = {
        "last_success_at": datetime.now(UTC) - timedelta(hours=1),
        "last_auto_date": datetime.now().astimezone().date().isoformat(),
        "last_auto_ok": True,
    }
    values.update(changes)
    backup_service.update_prefs(**values)


def test_no_password(client):
    text = card(client)
    assert "Set a backup password to start backing up." in text
    assert 'href="/backups"' in text


def test_stale(client, backup_password):
    healthy(last_success_at=datetime.now(UTC) - timedelta(days=8))
    assert "No backup in the last 7 days." in card(client)


def test_no_backups(client, backup_password):
    healthy(last_success_at=None)
    assert "No backups yet." in card(client)


def test_healthy_shows_a_quiet_line(client, backup_password):
    healthy()
    text = card(client)
    expected = backup_service.load_prefs().last_success_at.astimezone().strftime("%H:%M")
    assert f"Last backup: today at {expected}" in text
    assert "Go to Backups" not in text


def test_dashboard_stays_fast_with_many_backups(client, backup_password, data_dir):
    healthy()
    for i in range(40):
        write_db_backup(
            data_dir / "backups",
            b"x",
            name=f"FloorPro-backup-2026-10-{i % 28 + 1:02d}-09{i:04d}-manual.fpbackup",
        )
    client.get("/")
    started = time.perf_counter()
    response = client.get("/")
    assert response.status_code == 200
    assert time.perf_counter() - started < 0.3
