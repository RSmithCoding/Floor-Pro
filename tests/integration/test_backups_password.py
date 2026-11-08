"""Backups screen and the backup password (US5)."""

from __future__ import annotations

import base64
import json

from floorpro import backup_file
from tests.conftest import BACKUP_PASSWORD, page_text


def test_backups_page_renders_with_nav(client):
    response = client.get("/backups")
    assert response.status_code == 200
    assert "<title>Backups · FloorPro</title>" in response.text
    assert 'href="/backups" class="' in response.text
    nav_link = response.text.split('href="/backups"', 1)[1].split(">", 1)[0]
    assert 'aria-current="page"' in nav_link


GOOD = "a long enough password"


def key_file(data_dir):
    return json.loads((data_dir / "backup-key.json").read_text())


def test_no_password_shows_only_the_set_form(client):
    text = page_text(client.get("/backups"))
    assert 'id="backup-password-form"' in text
    assert 'type="password"' in text
    assert 'autocomplete="new-password"' in text
    assert "Write this password down and keep it somewhere safe" in text
    assert "If it's forgotten, backups made with it can never be restored" in text
    assert "Back up now" not in text


def test_short_password_is_rejected(client, data_dir):
    secret = "123456789"
    response = client.post(
        "/backups/password", data={"password": secret, "password_confirm": secret}
    )
    assert response.status_code == 422
    assert "Use at least 10 characters." in page_text(response)
    assert secret not in response.text
    assert not (data_dir / "backup-key.json").exists()


def test_mismatched_passwords_are_rejected(client, data_dir):
    response = client.post(
        "/backups/password", data={"password": GOOD, "password_confirm": GOOD + "x"}
    )
    assert response.status_code == 422
    assert "The two passwords don't match." in page_text(response)
    assert GOOD not in response.text
    assert not (data_dir / "backup-key.json").exists()


def test_set_form_errors_are_swapped_in_place_for_htmx(client, htmx):
    response = client.post(
        "/backups/password", data={"password": "short", "password_confirm": "short"}, headers=htmx
    )
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#backup-password-form"
    assert "Use at least 10 characters." in page_text(response)


def test_valid_password_is_stored_as_a_key(client, data_dir):
    response = client.post("/backups/password", data={"password": GOOD, "password_confirm": GOOD})
    assert response.status_code == 200
    assert "Backup password set" in page_text(response)
    stored = key_file(data_dir)
    key = base64.b64decode(stored["key"])
    assert base64.b64decode(stored["key_id"]) == backup_file.key_id(key)
    assert set(stored) == {"version", "kdf", "key", "key_id", "set_at"}
    raw = (data_dir / "backup-key.json").read_text()
    assert GOOD not in raw


def test_password_can_only_be_set_once(client, backup_password):
    response = client.post("/backups/password", data={"password": GOOD, "password_confirm": GOOD})
    assert response.status_code == 409


def test_change_dialog(client, backup_password):
    text = page_text(client.get("/backups/password/change"))
    assert "<dialog" in text
    assert "Backups you've already made still need the password they were made with." in text
    assert 'autocomplete="current-password"' in text


def test_change_needs_the_current_password(client, backup_password, htmx):
    response = client.post(
        "/backups/password/change",
        data={"current_password": "", "password": GOOD, "password_confirm": GOOD},
        headers=htmx,
    )
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#modal"
    assert "Enter your current backup password." in page_text(response)

    response = client.post(
        "/backups/password/change",
        data={"current_password": "not the password", "password": GOOD, "password_confirm": GOOD},
        headers=htmx,
    )
    assert response.status_code == 422
    assert "That isn't the current backup password." in page_text(response)


def test_change_validates_the_new_password(client, backup_password, htmx):
    response = client.post(
        "/backups/password/change",
        data={"current_password": BACKUP_PASSWORD, "password": "short", "password_confirm": "x"},
        headers=htmx,
    )
    assert response.status_code == 422
    text = page_text(response)
    assert "Use at least 10 characters." in text
    assert "The two passwords don't match." in text


def test_change_password(client, backup_password, data_dir):
    before = key_file(data_dir)
    response = client.post(
        "/backups/password/change",
        data={"current_password": BACKUP_PASSWORD, "password": GOOD, "password_confirm": GOOD},
    )
    assert response.status_code == 200
    assert "Backup password changed" in page_text(response)
    after = key_file(data_dir)
    assert after["key_id"] != before["key_id"]
    assert after["kdf"]["salt"] != before["kdf"]["salt"]
