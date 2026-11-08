"""Pure backup rules: names, retention, status and password checks (data-model §1, §4, §6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from floorpro.domain import backups as d
from floorpro.domain.backups import BackupInfo, BackupKind, BackupPrefs

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def info(kind, minutes_ago, *, damaged=False, location="local", name=None):
    created = NOW - timedelta(minutes=minutes_ago)
    return BackupInfo(
        location=location,
        filename=name or f"{kind}-{minutes_ago}.fpbackup",
        kind=None if damaged else kind,
        created_at=created,
        app_version="0.2.0",
        schema_revision="0001",
        contents={"customers": 1},
        size_bytes=100,
        protected=True,
        key_id=b"k" * 16,
        damaged=damaged,
    )


# --- BackupKind ------------------------------------------------------------------------------


def test_kinds_and_labels():
    assert [k.value for k in BackupKind] == [
        "manual",
        "automatic",
        "before_restore",
        "before_upgrade",
    ]
    assert [k.label for k in BackupKind] == [
        "Manual",
        "Automatic",
        "Before restore",
        "Before upgrade",
    ]


# --- filenames -------------------------------------------------------------------------------

LOCAL = datetime(2026, 11, 8, 17, 30, 12)


def test_filename_for():
    assert (
        d.filename_for(BackupKind.MANUAL, LOCAL, set())
        == "FloorPro-backup-2026-11-08-173012-manual.fpbackup"
    )
    assert d.filename_for(BackupKind.BEFORE_RESTORE, LOCAL, set()).endswith(
        "-before-restore.fpbackup"
    )
    assert d.filename_for(BackupKind.BEFORE_UPGRADE, LOCAL, set()).endswith(
        "-before-upgrade.fpbackup"
    )


def test_filename_collisions_get_a_suffix():
    first = d.filename_for(BackupKind.MANUAL, LOCAL, set())
    second = d.filename_for(BackupKind.MANUAL, LOCAL, {first})
    third = d.filename_for(BackupKind.MANUAL, LOCAL, {first, second})
    assert second == "FloorPro-backup-2026-11-08-173012-manual-2.fpbackup"
    assert third == "FloorPro-backup-2026-11-08-173012-manual-3.fpbackup"


@pytest.mark.parametrize(
    "name",
    [
        "FloorPro-backup-2026-11-08-173012-manual.fpbackup",
        "FloorPro-backup-2026-11-08-173012-automatic-2.fpbackup",
        "FloorPro-backup-2026-11-08-173012-before-restore.fpbackup",
        "FloorPro-backup-2026-11-08-173012-before-upgrade.fpbackup",
    ],
)
def test_parse_filename_accepts(name):
    parsed = d.parse_filename(name)
    assert parsed is not None and not parsed.legacy


def test_parse_legacy_filename():
    parsed = d.parse_filename("floorpro-20261107T101500123456Z-pre-0001.db")
    assert parsed is not None and parsed.legacy
    assert parsed.kind is BackupKind.BEFORE_UPGRADE
    assert parsed.created_at == datetime(2026, 11, 7, 10, 15, 0, 123456, tzinfo=UTC)


@pytest.mark.parametrize(
    "name",
    [
        "../x.fpbackup",
        "../FloorPro-backup-2026-11-08-173012-manual.fpbackup",
        "/etc/FloorPro-backup-2026-11-08-173012-manual.fpbackup",
        "C:\\FloorPro-backup-2026-11-08-173012-manual.fpbackup",
        "FloorPro-backup-2026-11-08-173012-weekly.fpbackup",
        "FloorPro-backup-2026-11-08-173012-manual.fpbackup.partial",
        "floorpro.db",
        "",
    ],
)
def test_parse_filename_rejects(name):
    assert d.parse_filename(name) is None


# --- retention and most recent ---------------------------------------------------------------


def test_select_for_pruning():
    backups = (
        [info(BackupKind.AUTOMATIC, i) for i in range(16)]
        + [info(BackupKind.MANUAL, 1000 + i) for i in range(20)]
        + [info(BackupKind.BEFORE_RESTORE, 2000 + i) for i in range(20)]
        + [info(BackupKind.BEFORE_UPGRADE, 3000 + i) for i in range(12)]
    )
    pruned = d.select_for_pruning(backups)
    automatic = [b for b in pruned if b.kind is BackupKind.AUTOMATIC]
    upgrade = [b for b in pruned if b.kind is BackupKind.BEFORE_UPGRADE]
    assert sorted(b.filename for b in automatic) == [
        "automatic-14.fpbackup",
        "automatic-15.fpbackup",
    ]
    assert sorted(b.filename for b in upgrade) == [
        "before_upgrade-3010.fpbackup",
        "before_upgrade-3011.fpbackup",
    ]
    assert len(pruned) == 4


def test_pruning_ignores_damaged_files():
    backups = [info(BackupKind.AUTOMATIC, i) for i in range(14)] + [info(None, 99, damaged=True)]
    assert d.select_for_pruning(backups) == []


def test_most_recent_any_kind_ignores_damaged():
    newest = info(BackupKind.BEFORE_RESTORE, 5, location="folder")
    backups = [info(BackupKind.MANUAL, 10), newest, info(None, 1, damaged=True)]
    assert d.most_recent(backups) is newest
    assert d.most_recent([]) is None


def test_needs_password():
    b = info(BackupKind.MANUAL, 1)
    assert not b.needs_password(b"k" * 16)
    assert b.needs_password(b"z" * 16)
    assert b.needs_password(None)


# --- dashboard status ------------------------------------------------------------------------


def messages(prefs, key_set=True, now=NOW):
    return [w.message for w in d.backup_status(prefs, key_set, now)]


def test_status_healthy():
    assert messages(BackupPrefs(last_success_at=NOW - timedelta(hours=2))) == []


def test_status_all_warnings_in_order():
    prefs = BackupPrefs(
        auto_enabled=False,
        last_auto_ok=False,
        last_auto_error="The disk is full.",
        last_fallback_at=NOW,
        last_success_at=None,
    )
    assert messages(prefs, key_set=False) == [
        "Set a backup password to start backing up.",
        "The last automatic backup failed: The disk is full.",
        "Your backup folder couldn't be reached, so backups were saved on this computer.",
        "Automatic backups are off.",
        "No backups yet.",
    ]


def test_status_stale_boundary():
    exactly = BackupPrefs(last_success_at=NOW - timedelta(days=7))
    over = BackupPrefs(last_success_at=NOW - timedelta(days=7, seconds=1))
    assert messages(exactly) == []
    assert messages(over) == ["No backup in the last 7 days."]


# --- password rules --------------------------------------------------------------------------


def test_password_rules():
    assert d.validate_new_password("123456789", "123456789") == {
        "password": "Use at least 10 characters."
    }
    assert d.validate_new_password(" " * 12, " " * 12) == {
        "password": "Use at least 10 characters."
    }
    long = "x" * 1025
    assert d.validate_new_password(long, long) == {"password": "Use at most 1,024 characters."}
    assert d.validate_new_password("x" * 1024, "x" * 1024) == {}
    assert d.validate_new_password("long enough pw", "long enough pX") == {
        "password_confirm": "The two passwords don't match."
    }
    assert d.validate_new_password("long enough pw", "long enough pw") == {}


def test_password_length_counts_after_nfc():
    import unicodedata

    nfc = "é" * 9 + "!"  # 10 characters in NFC
    nfd = unicodedata.normalize("NFD", nfc)  # 19 code points
    assert d.validate_new_password(nfd, nfd) == {}
    short_nfd = unicodedata.normalize("NFD", "é" * 9)  # 18 code points, 9 characters
    assert d.validate_new_password(short_nfd, short_nfd) == {
        "password": "Use at least 10 characters."
    }
