"""Restore from a file, including a backup from another computer (US4, FR-029)."""

from __future__ import annotations

import re
import shutil

import pytest
from fastapi.testclient import TestClient

from floorpro.app import create_app
from floorpro.services import backup_service
from tests.conftest import page_text

FIXTURE_PASSWORD = "correct horse battery"


@pytest.fixture
def fixture_copy(tmp_path):
    from tests.integration.test_backup_fixture import FIXTURE

    target = tmp_path / "from-another-pc.fpbackup"
    shutil.copyfile(FIXTURE, target)
    return target


@pytest.fixture
def other_password(client):
    backup_service.set_password("this computer's own password")


def token_of(text):
    return re.search(r'name="source_token" value="([^"]+)"', text).group(1)


def choose(client, fake_dialogs, path, prefix="/backups"):
    fake_dialogs.open_result = path
    response = client.post(f"{prefix}/restore-file/choose", headers={"HX-Request": "true"})
    assert response.status_code == 200
    return page_text(response)


def customer_names(client):
    return page_text(client.get("/customers?archived=1"))


def test_choose_shows_the_dialog_with_a_password_field(
    client, fake_dialogs, other_password, fixture_copy
):
    text = choose(client, fake_dialogs, fixture_copy)
    assert "<dialog" in text
    assert token_of(text)
    assert 'name="password"' in text
    assert "3 customers" in text


def test_choose_cancelled(client, fake_dialogs, other_password):
    fake_dialogs.open_result = None
    assert client.post("/backups/restore-file/choose").status_code == 204


def test_confirm_needs_the_password(client, fake_dialogs, other_password, fixture_copy):
    token = token_of(choose(client, fake_dialogs, fixture_copy))
    response = client.post(
        "/backups/restore-file/confirm", data={"source_token": token, "confirm": "RESTORE"}
    )
    assert response.status_code == 422
    assert "Enter the password this backup was made with." in page_text(response)


def test_confirm_wrong_password(client, fake_dialogs, other_password, fixture_copy, data_dir):
    from tests.conftest import db_dump

    before = db_dump(data_dir / "floorpro.db")
    token = token_of(choose(client, fake_dialogs, fixture_copy))
    response = client.post(
        "/backups/restore-file/confirm",
        data={"source_token": token, "confirm": "RESTORE", "password": "not it at all"},
    )
    assert response.status_code == 422
    assert "That password doesn't open this backup." in page_text(response)
    assert db_dump(data_dir / "floorpro.db") == before


def test_confirm_correct_password(client, fake_dialogs, other_password, fixture_copy):
    token = token_of(choose(client, fake_dialogs, fixture_copy))
    response = client.post(
        "/backups/restore-file/confirm",
        data={"source_token": token, "confirm": "RESTORE", "password": FIXTURE_PASSWORD},
    )
    assert response.status_code == 200
    text = customer_names(client)
    assert "Lovelace" in text
    assert "Brunel Flooring Ltd" in text


def test_upload(client, other_password, fixture_copy):
    with open(fixture_copy, "rb") as fh:
        response = client.post(
            "/backups/restore-file/upload",
            files={"file": ("backup.fpbackup", fh, "application/octet-stream")},
        )
    assert response.status_code == 200
    text = page_text(response)
    token = token_of(text)
    response = client.post(
        "/backups/restore-file/confirm",
        data={"source_token": token, "confirm": "RESTORE", "password": FIXTURE_PASSWORD},
    )
    assert response.status_code == 200
    assert "Lovelace" in customer_names(client)


def test_upload_not_a_backup(client, other_password):
    response = client.post(
        "/backups/restore-file/upload",
        files={"file": ("x.fpbackup", b"%PDF-1.7\n" + b"x" * 400, "application/pdf")},
    )
    assert response.status_code == 422
    assert "This file isn't a FloorPro backup, or it's damaged." in page_text(response)


def test_bad_token(client, other_password):
    response = client.post(
        "/backups/restore-file/confirm",
        data={"source_token": "dGFtcGVyZWQ.abc", "confirm": "RESTORE"},
    )
    assert response.status_code == 409
    assert "That file is no longer available. Choose it again." in page_text(response)


def test_restore_from_a_file_in_recovery(data_dir, fixture_copy):
    with TestClient(create_app(data_dir)):
        pass
    with open(data_dir / "floorpro.db", "r+b") as fh:
        fh.write(b"\x00garbage!" * 12)
    app = create_app(data_dir)
    with TestClient(app) as client:
        with open(fixture_copy, "rb") as fh:
            response = client.post(
                "/recovery/restore-file/upload",
                files={"file": ("backup.fpbackup", fh, "application/octet-stream")},
            )
        assert response.status_code == 200
        token = token_of(page_text(response))
        response = client.post(
            "/recovery/restore-file/confirm",
            data={"source_token": token, "confirm": "RESTORE", "password": FIXTURE_PASSWORD},
        )
        assert response.status_code == 200
        assert "Lovelace" in customer_names(client)
        assert app.state.recovery is None
