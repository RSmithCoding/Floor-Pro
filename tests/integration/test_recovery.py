"""Startup recovery when the shop's database can't be opened (FR-025)."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from floorpro.app import create_app
from floorpro.services import backup_service
from tests.conftest import BACKUP_PASSWORD, make_customer, page_text


def damage(db_path):
    with open(db_path, "r+b") as fh:
        fh.write(b"\x00garbage!" * 12)


@pytest.fixture
def prepared(data_dir):
    """A database with one customer and a backup of it, made by a normal run."""
    app = create_app(data_dir)
    with TestClient(app) as client:
        backup_service.set_password(BACKUP_PASSWORD)
        with app.state.sessionmaker() as session:
            make_customer(session, first_name="Rescued")
        client.post("/backups")
    return data_dir


def broken_client(data_dir):
    damage(data_dir / "floorpro.db")
    return TestClient(create_app(data_dir))


def test_garbage_database_enters_recovery(prepared, htmx):
    with broken_client(prepared) as client:
        assert client.get("/healthz").status_code == 200
        response = client.get("/customers", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/recovery"
        response = client.get("/customers", headers=htmx, follow_redirects=False)
        assert response.headers["HX-Redirect"] == "/recovery"
        assert client.get("/static/css/app.css").status_code == 200


def test_recovery_screen(prepared):
    with broken_client(prepared) as client:
        text = page_text(client.get("/recovery"))
        assert "FloorPro couldn't open your shop's data. It may have been damaged." in text
        assert "Restore this backup" in text
        assert "Start with no data" in text
        assert "Restore from a file" in text


def test_restore_in_recovery(prepared):
    backup = next((prepared / "backups").glob("*.fpbackup"))
    with broken_client(prepared) as client:
        response = client.post(
            "/recovery/restore", data={"loc": "local", "name": backup.name}, follow_redirects=False
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        home = page_text(client.get("/"))
        assert "Restored the backup from" in home
        assert "Rescued" in page_text(client.get("/customers"))
        assert client.get("/recovery").status_code == 404
    damaged = list((prepared / "damaged").glob("floorpro-*.db"))
    assert len(damaged) == 1
    assert b"garbage" in damaged[0].read_bytes()


def test_start_fresh(prepared):
    with broken_client(prepared) as client:
        response = client.post("/recovery/start-fresh", data={"confirm": "start again"})
        assert response.status_code == 422
        assert "Type START AGAIN to confirm." in page_text(response)
        response = client.post("/recovery/start-fresh", data={"confirm": "START AGAIN"})
        assert response.status_code == 200
        text = page_text(response)
        assert "Started with no data. The damaged data was kept in" in text
        assert "Rescued" not in page_text(client.get("/customers"))
    assert len(list((prepared / "damaged").glob("floorpro-*.db"))) == 1


def test_no_backups(data_dir):
    with TestClient(create_app(data_dir)):
        pass
    with broken_client(data_dir) as client:
        text = page_text(client.get("/recovery"))
        assert "Restore this backup" not in text
        assert "Start with no data" in text
        assert "Restore from a file" in text


def test_legacy_copy_restores_in_recovery(data_dir):
    with TestClient(create_app(data_dir)) as client, client.app.state.sessionmaker() as session:
        make_customer(session, first_name="Legacy")
    legacy = data_dir / "backups" / "floorpro-20261101T090000000000Z-pre-0001.db"
    legacy.parent.mkdir(exist_ok=True)
    shutil.copyfile(data_dir / "floorpro.db", legacy)
    with broken_client(data_dir) as client:
        assert "Restore this backup" in page_text(client.get("/recovery"))
        client.post("/recovery/restore", data={"loc": "local", "name": legacy.name})
        assert "Legacy" in page_text(client.get("/customers"))


def test_failed_migration_enters_recovery(data_dir, monkeypatch):
    import floorpro.app as app_module

    def broken_upgrade(*_args, **_kwargs):
        raise RuntimeError("alembic exploded")

    monkeypatch.setattr(app_module, "upgrade_to_head", broken_upgrade)
    with TestClient(create_app(data_dir)) as client:
        response = client.get("/", follow_redirects=False)
        assert response.headers["location"] == "/recovery"
