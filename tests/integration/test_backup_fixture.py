"""The committed cross-platform fixture restores identically on macOS and Windows (SC-006)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from floorpro import backup_file
from floorpro.services import backup_service
from tests.conftest import db_dump, make_customer

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "backup-v1.fpbackup"
PASSWORD = "correct horse battery"


def test_fixture_restores_to_the_known_contents(tmp_path):
    header = backup_file.read_header(FIXTURE)
    assert header["format_version"] == 1
    assert header["schema_revision"] == "0001"
    assert header["contents"] == {"customers": 3}
    key = backup_file.derive_key(PASSWORD, backup_file.KdfParams.from_header(header["kdf"]))
    db = tmp_path / "fixture.db"
    db.write_bytes(backup_file.decrypt(FIXTURE, key))
    with sqlite3.connect(db) as conn:
        customers = conn.execute(
            "SELECT id, customer_type, first_name, last_name, company_name, mobile_phone, "
            "other_phone, postcode, is_archived FROM customer ORDER BY id"
        ).fetchall()
        settings = conn.execute(
            "SELECT currency_code, vat_registered, vat_rate_bp, vat_number, price_entry_mode "
            "FROM business_settings"
        ).fetchall()
        history = conn.execute("SELECT field, old_value, new_value FROM settings_change").fetchall()
    assert customers == [
        (1, "domestic", "Ada", "Lovelace", None, "07700 900001", None, "SW1A 1AA", 0),
        (2, "trade", None, None, "Brunel Flooring Ltd", None, "0117 496 0002", None, 0),
        (3, "domestic", "Charles", "Babbage", None, "07700 900003", None, None, 1),
    ]
    assert settings == [("GBP", 1, 1750, None, "inc_vat")]
    assert history == [("vat_rate", "20.00", "17.50")]


def test_backup_made_on_this_runner_round_trips(client, session, backup_password, data_dir):
    make_customer(session, first_name="Zoë", notes="Line one\nLine two — ünïcödé")
    client.post("/backups")
    path = next((data_dir / "backups").glob("*-manual.fpbackup"))
    copy = data_dir / "copy.db"
    copy.write_bytes(backup_file.decrypt(path, backup_service.load_key().key))
    assert db_dump(copy) == db_dump(data_dir / "floorpro.db")
