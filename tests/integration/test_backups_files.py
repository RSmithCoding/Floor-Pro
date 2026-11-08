"""Backup folder, Save a copy, download and delete (US4, FR-021 to FR-024)."""

from __future__ import annotations

import os
import shutil

import pytest

from floorpro.services import backup_service
from tests.conftest import page_text
from tests.integration.backup_helpers import only_backup

UNREACHABLE = "can't be reached. Is the drive plugged in?"


@pytest.fixture
def usb(tmp_path):
    folder = tmp_path / "usb"
    folder.mkdir()
    return folder


# --- Choosing a folder -----------------------------------------------------------------------


def test_choose_folder_desktop(client, fake_dialogs, backup_password, usb):
    fake_dialogs.folder_result = usb
    response = client.post("/backups/folder/choose")
    assert response.status_code == 200
    text = page_text(response)
    assert f"Backups will be saved to {usb}" in text
    assert str(usb) in text.split('id="backup-panel"', 1)[1]
    client.post("/backups")
    assert len(list(usb.glob("FloorPro-backup-*-manual.fpbackup"))) == 1


def test_choose_folder_cancelled(client, fake_dialogs, backup_password):
    fake_dialogs.folder_result = None
    response = client.post("/backups/folder/choose")
    assert response.status_code == 204
    assert backup_service.load_prefs().folder is None


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions")
def test_choose_read_only_folder(client, fake_dialogs, backup_password, usb):
    usb.chmod(0o500)
    try:
        fake_dialogs.folder_result = usb
        response = client.post("/backups/folder/choose")
        assert "Choose a folder FloorPro can save to." in page_text(response)
        assert backup_service.load_prefs().folder is None
    finally:
        usb.chmod(0o700)


def test_choose_folder_needs_the_desktop_window(client, backup_password):
    assert client.post("/backups/folder/choose").status_code == 404


@pytest.mark.parametrize("value", ["relative/folder", "", "MISSING", "FILE"])
def test_folder_by_path_is_validated(client, backup_password, usb, value):
    if value == "MISSING":
        value = str(usb / "nope")
    elif value == "FILE":
        (usb / "a.txt").write_text("x")
        value = str(usb / "a.txt")
    response = client.post("/backups/folder", data={"folder": value})
    assert response.status_code == 422
    assert "Choose a folder FloorPro can save to." in page_text(response)
    assert backup_service.load_prefs().folder is None


def test_folder_by_path(client, backup_password, usb):
    response = client.post("/backups/folder", data={"folder": str(usb)})
    assert f"Backups will be saved to {usb}" in page_text(response)
    assert backup_service.load_prefs().folder == str(usb)


def test_reset_folder(client, backup_password, usb):
    backup_service.set_folder(usb)
    client.post("/backups")
    response = client.post("/backups/folder/reset")
    assert "Backups will be saved on this computer" in page_text(response)
    assert backup_service.load_prefs().folder is None
    assert len(list(usb.glob("*.fpbackup"))) == 1  # left where it was


# --- A missing folder ------------------------------------------------------------------------


def test_missing_folder_manual_backup(client, backup_password, usb, data_dir):
    backup_service.set_folder(usb)
    shutil.rmtree(usb)
    response = client.post("/backups")
    text = page_text(response)
    assert f"The backup folder {usb} {UNREACHABLE}" in text
    assert list((data_dir / "backups").glob("*.fpbackup")) == []


def test_missing_folder_automatic_backup_falls_back(client, backup_password, usb, data_dir):
    backup_service.set_folder(usb)
    shutil.rmtree(usb)
    backup_service.run_automatic()
    assert len(list((data_dir / "backups").glob("*-automatic.fpbackup"))) == 1
    prefs = backup_service.load_prefs()
    assert prefs.last_fallback_at is not None
    assert prefs.last_auto_ok is True
    text = page_text(client.get("/"))
    assert "Your backup folder couldn't be reached, so backups were saved on this computer." in text

    usb.mkdir()
    client.post("/backups")
    assert backup_service.load_prefs().last_fallback_at is None


# --- Save a copy -----------------------------------------------------------------------------


def test_save_a_copy_desktop(client, fake_dialogs, backup_password, data_dir, tmp_path):
    client.post("/backups")
    backup = only_backup(data_dir)
    target = tmp_path / "Desktop-copy.fpbackup"
    fake_dialogs.save_result = target
    response = client.post(f"/backups/local/{backup.name}/save-copy")
    assert response.status_code == 200
    assert f"Saved a copy to {target}" in page_text(response)
    assert fake_dialogs.saved_names == [backup.name]
    assert target.read_bytes() == backup.read_bytes()


def test_save_a_copy_cancelled(client, fake_dialogs, backup_password, data_dir):
    client.post("/backups")
    backup = only_backup(data_dir)
    fake_dialogs.save_result = None
    response = client.post(f"/backups/local/{backup.name}/save-copy")
    assert response.status_code == 204


def test_download(client, backup_password, data_dir):
    client.post("/backups")
    backup = only_backup(data_dir)
    response = client.get(f"/backups/local/{backup.name}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"] == f'attachment; filename="{backup.name}"'
    assert response.content == backup.read_bytes()


# --- Delete ----------------------------------------------------------------------------------


def test_delete(client, backup_password, data_dir):
    client.post("/backups")
    older = only_backup(data_dir)
    client.post("/backups")
    dialog = page_text(client.get(f"/backups/local/{older.name}/delete"))
    assert "<dialog" in dialog
    assert "This can't be undone." in dialog
    response = client.post(f"/backups/local/{older.name}/delete")
    assert "Backup deleted" in page_text(response)
    assert not older.exists()


def test_most_recent_backup_cannot_be_deleted(client, backup_password, data_dir):
    client.post("/backups")
    latest = only_backup(data_dir)
    response = client.get(f"/backups/local/{latest.name}/delete")
    assert response.status_code == 409
    assert "most recent backup" in page_text(response)
    assert client.post(f"/backups/local/{latest.name}/delete").status_code == 409
    assert latest.exists()
