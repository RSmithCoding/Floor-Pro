from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from floorpro.app import create_app
from floorpro.models import Customer

HTMX = {"HX-Request": "true"}


BACKUP_PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    """Cheap scrypt parameters for tests; the production default is checked separately."""
    from floorpro import backup_file

    monkeypatch.setattr(backup_file, "DEFAULT_KDF", backup_file.KdfParams(n=2**10, r=8, p=1))


@pytest.fixture(autouse=True)
def inline_background(monkeypatch):
    """Background work (automatic backups) runs inline in tests unless a test opts out."""
    import floorpro.app

    monkeypatch.setattr(floorpro.app, "_start_thread", lambda fn: fn())


class FakeDialogs:
    """Stands in for the native dialogs; tests set what each one returns (None = cancelled)."""

    def __init__(self):
        self.save_result: Path | None = None
        self.folder_result: Path | None = None
        self.open_result: Path | None = None
        self.saved_names: list[str] = []

    def save_path(self, filename: str) -> Path | None:
        self.saved_names.append(filename)
        return self.save_result

    def choose_folder(self) -> Path | None:
        return self.folder_result

    def open_file(self) -> Path | None:
        return self.open_result


@pytest.fixture
def fake_dialogs(app):
    dialogs = FakeDialogs()
    app.state.dialogs = dialogs
    return dialogs


@pytest.fixture
def sync_background(app):
    """Run 'background' work (automatic backups) inline, so tests can assert on it."""
    app.state.run_in_background = lambda fn: fn()
    return app


@pytest.fixture
def backup_password(client):
    from floorpro.services import backup_service

    backup_service.set_password(BACKUP_PASSWORD)
    return BACKUP_PASSWORD


def db_dump(path: Path) -> str:
    """Full SQL dump of a database, for exactness checks."""
    conn = sqlite3.connect(path)
    try:
        return "\n".join(conn.iterdump())
    finally:
        conn.close()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORPRO_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def app(data_dir):
    return create_app(data_dir)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(client, app):
    with app.state.sessionmaker() as db_session:
        yield db_session


@pytest.fixture
def htmx():
    return dict(HTMX)


def make_customer(session, **overrides) -> Customer:
    """Insert a valid domestic customer (derived columns computed) and commit."""
    from floorpro.domain.validation import normalise_postcode, phone_digits, postcode_compact

    now = datetime.now(UTC)
    values = dict(
        customer_type="domestic",
        show_vat_breakdown=False,
        first_name="Jane",
        last_name="Smith",
        mobile_phone="07700 900123",
        marketing_consent=False,
        is_archived=False,
        created_at=now,
        updated_at=now,
    )
    values.update(overrides)
    for field in ("mobile_phone", "other_phone"):
        values[f"{field}_digits"] = phone_digits(values[field]) if values.get(field) else None
    if values.get("postcode"):
        values["postcode"] = normalise_postcode(values["postcode"])[0]
        values["postcode_compact"] = postcode_compact(values["postcode"])
    customer = Customer(**values)
    session.add(customer)
    session.commit()
    return customer


def page_text(response) -> str:
    """Response HTML with entities decoded, so assertions can use plain apostrophes."""
    import html

    return html.unescape(response.text)
