import sqlite3
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from floorpro.db import make_engine
from floorpro.migrate import KEEP_BACKUPS, head_revision, upgrade_to_head
from floorpro.models import Base, BusinessSettings, Customer, SettingsChange


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORPRO_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def db_path(data_dir):
    return data_dir / "floorpro.db"


def backups(data_dir):
    folder = data_dir / "backups"
    return sorted(folder.glob("floorpro-*-pre-*.db")) if folder.exists() else []


NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def customer_row(**overrides):
    row = dict(
        customer_type="domestic",
        show_vat_breakdown=False,
        first_name="Jane",
        last_name="Smith",
        mobile_phone="07700 900123",
        mobile_phone_digits="07700900123",
        marketing_consent=False,
        is_archived=False,
        created_at=NOW,
        updated_at=NOW,
    )
    row.update(overrides)
    return row


def test_empty_database_upgrades_to_head_and_matches_models(db_path):
    upgrade_to_head(db_path)
    engine = make_engine(db_path)
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        assert context.get_current_revision() == head_revision()
        assert compare_metadata(context, Base.metadata) == []
    engine.dispose()


@pytest.mark.parametrize(
    "table, row",
    [
        (
            BusinessSettings,
            dict(
                id=2,
                currency_code="GBP",
                vat_registered=True,
                vat_rate_bp=Decimal("20"),
                price_entry_mode="inc_vat",
                updated_at=NOW,
            ),
        ),
        (
            BusinessSettings,
            dict(
                id=1,
                currency_code="GBP",
                vat_registered=True,
                vat_rate_bp=Decimal("20"),
                price_entry_mode="gross",
                updated_at=NOW,
            ),
        ),
        (SettingsChange, dict(change_set_id="x", changed_at=NOW, field="colour")),
        (Customer, customer_row(customer_type="wholesale")),
        (Customer, customer_row(customer_type="trade", show_vat_breakdown=False)),
        (Customer, customer_row(first_name=" ", last_name=None, company_name=None)),
        (Customer, customer_row(mobile_phone=None, mobile_phone_digits=None)),
    ],
)
def test_check_constraints_are_enforced(db_path, table, row):
    upgrade_to_head(db_path)
    engine = make_engine(db_path)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(table), [row])
    engine.dispose()


def test_vat_rate_range_constraint(db_path):
    upgrade_to_head(db_path)
    with sqlite3.connect(db_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO business_settings VALUES (1, 'GBP', 1, 10001, NULL, 'inc_vat', ?)",
            (NOW.replace(tzinfo=None).isoformat(),),
        )


def test_backup_created_before_migrating_existing_database(data_dir, db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE legacy (value TEXT)")
        conn.execute("INSERT INTO legacy VALUES ('keep me')")

    upgrade_to_head(db_path)

    files = backups(data_dir)
    assert len(files) == 1
    assert f"-pre-{head_revision()}" in files[0].name
    with sqlite3.connect(files[0]) as conn:
        assert conn.execute("SELECT value FROM legacy").fetchall() == [("keep me",)]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT value FROM legacy").fetchall() == [("keep me",)]


def test_no_backup_for_new_or_up_to_date_database(data_dir, db_path):
    upgrade_to_head(db_path)
    upgrade_to_head(db_path)
    assert backups(data_dir) == []


def test_only_newest_backups_kept(data_dir, db_path):
    folder = data_dir / "backups"
    folder.mkdir()
    for i in range(12):
        (folder / f"floorpro-20260101T0000{i:02d}000000Z-pre-0000.db").write_bytes(b"")
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE legacy (value TEXT)")

    upgrade_to_head(db_path)

    files = backups(data_dir)
    assert len(files) == KEEP_BACKUPS
    assert files[0].name == "floorpro-20260101T000003000000Z-pre-0000.db"


def test_realistic_data_survives_upgrade(db_path):
    """Principle III: future migrations must extend this fixture with their previous schema."""
    upgrade_to_head(db_path)
    engine = make_engine(db_path)
    customers = [
        customer_row(),
        customer_row(
            customer_type="trade",
            show_vat_breakdown=True,
            company_name="Acme Flooring",
            first_name=None,
            last_name=None,
            email="ACCOUNTS@acme.example",
            mobile_phone=None,
            mobile_phone_digits=None,
        ),
        customer_row(is_archived=True, archived_at=NOW, title="Dr", last_name="Jones"),
        customer_row(show_vat_breakdown=True, notes="Insurance job " * 100),
        customer_row(
            title="Mrs",
            first_name="Ann",
            last_name="Lee",
            company_name="Lee Lettings",
            other_phone="0117 496 0000",
            other_phone_digits="01174960000",
            email="ann@example.com",
            address_line1="1 High Street",
            address_line2="Flat 2",
            town="Bristol",
            county="Avon",
            postcode="BS1 4DJ",
            postcode_compact="BS14DJ",
            marketing_consent=True,
        ),
    ]
    with engine.begin() as conn:
        conn.execute(
            insert(BusinessSettings),
            [
                dict(
                    id=1,
                    currency_code="EUR",
                    vat_registered=False,
                    vat_rate_bp=Decimal("17.5"),
                    vat_number="GB123456789",
                    price_entry_mode="ex_vat",
                    updated_at=NOW,
                )
            ],
        )
        conn.execute(
            insert(SettingsChange),
            [
                dict(
                    change_set_id="a",
                    changed_at=NOW,
                    field="vat_rate",
                    old_value="20.00",
                    new_value="17.50",
                ),
                dict(
                    change_set_id="a",
                    changed_at=NOW,
                    field="currency_code",
                    old_value="GBP",
                    new_value="EUR",
                ),
                dict(
                    change_set_id="b",
                    changed_at=NOW,
                    field="vat_registered",
                    old_value="true",
                    new_value="false",
                ),
            ],
        )
        for row in customers:  # rows have different keys, so insert one at a time
            conn.execute(insert(Customer).values(**row))

    def snapshot():
        with engine.connect() as conn:
            return {
                t.name: [tuple(r) for r in conn.execute(select(t).order_by(*t.primary_key))]
                for t in (BusinessSettings.__table__, SettingsChange.__table__, Customer.__table__)
            }

    before = snapshot()
    engine.dispose()
    upgrade_to_head(db_path)
    engine = make_engine(db_path)
    assert snapshot() == before
    assert len(before["customer"]) == 5
    assert before["business_settings"][0][3] == Decimal("17.50")
    engine.dispose()


# --- Before upgrade backups once a backup password is set (feature 002) ---------------------


def _out_of_date_db(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE legacy (value TEXT)")
        conn.execute("INSERT INTO legacy VALUES ('keep me')")


def protected(data_dir):
    folder = data_dir / "backups"
    return sorted(folder.glob("FloorPro-backup-*-before-upgrade*.fpbackup"))


def test_no_password_still_writes_a_plain_copy(data_dir, db_path):
    _out_of_date_db(db_path)
    upgrade_to_head(db_path)
    assert len(backups(data_dir)) == 1
    assert protected(data_dir) == []


def test_password_set_writes_a_protected_before_upgrade_backup(data_dir, db_path):
    from floorpro import backup_file
    from floorpro.services import backup_service

    backup_service.set_password("correct horse battery")
    _out_of_date_db(db_path)
    upgrade_to_head(db_path)

    assert backups(data_dir) == []
    files = protected(data_dir)
    assert len(files) == 1
    assert backup_file.read_header(files[0])["kind"] == "before_upgrade"
    restored = backup_file.decrypt(files[0], backup_service.load_key().key)
    copy = data_dir / "check.db"
    copy.write_bytes(restored)
    with sqlite3.connect(copy) as conn:
        assert conn.execute("SELECT value FROM legacy").fetchall() == [("keep me",)]
    assert list((data_dir / "tmp").iterdir()) == []


def test_protected_before_upgrade_backups_keep_ten(data_dir, db_path):
    from datetime import timedelta

    from floorpro import backup_file
    from floorpro.domain.backups import BackupKind, filename_for
    from floorpro.services import backup_service

    backup_service.set_password("correct horse battery")
    stored = backup_service.load_key()
    folder = data_dir / "backups"
    for i in range(11):
        when = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
        fields = {
            "kind": "before_upgrade",
            "created_at": when.isoformat().replace("+00:00", "Z"),
            "app_version": "0.1.0",
            "schema_revision": None,
            "contents": {"customers": 0},
        }
        name = filename_for(BackupKind.BEFORE_UPGRADE, when.replace(tzinfo=None), set())
        backup_file.write_backup(folder, name, b"x", fields, stored.key, stored.kdf)
    _out_of_date_db(db_path)
    upgrade_to_head(db_path)

    files = protected(data_dir)
    assert len(files) == 10
    assert "2026-01-01" not in " ".join(f.name for f in files)
    assert "2026-01-02" not in " ".join(f.name for f in files)


def test_setting_the_password_protects_legacy_copies(data_dir, db_path):
    from floorpro import backup_file
    from floorpro.services import backup_service

    upgrade_to_head(db_path)
    folder = data_dir / "backups"
    folder.mkdir(exist_ok=True)
    legacy = folder / "floorpro-20261101T093000123456Z-pre-0001.db"
    with sqlite3.connect(db_path) as source, sqlite3.connect(legacy) as dest:
        source.backup(dest)

    backup_service.set_password("correct horse battery")

    assert not legacy.exists()
    files = protected(data_dir)
    assert len(files) == 1
    header = backup_file.read_header(files[0])
    assert header["kind"] == "before_upgrade"
    assert header["created_at"] == "2026-11-01T09:30:00.123456Z"
    assert header["schema_revision"] == head_revision()
    assert header["contents"] == {"customers": 0}


def test_restoring_an_older_backup_upgrades_it(data_dir, db_path):
    """A backup at an older revision (today: base) is upgraded on the staged copy, then swapped."""
    from alembic import command

    from floorpro import backup_file
    from floorpro.migrate import alembic_config, current_revision
    from floorpro.services import backup_service

    upgrade_to_head(db_path)
    backup_service.set_password("correct horse battery")

    old = data_dir / "old.db"
    with sqlite3.connect(db_path) as source, sqlite3.connect(old) as dest:
        source.backup(dest)
    engine = make_engine(old)
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "base")
    engine.dispose()
    assert current_revision(old) is None

    stored = backup_service.load_key()
    fields = {
        "kind": "manual",
        "created_at": "2026-11-01T09:00:00Z",
        "app_version": "0.0.1",
        "schema_revision": None,
        "contents": {"customers": 0},
    }
    path = backup_file.write_backup(
        data_dir / "backups",
        "FloorPro-backup-2026-11-01-090000-manual.fpbackup",
        old.read_bytes(),
        fields,
        stored.key,
        stored.kdf,
    )
    live = make_engine(db_path)
    backup_service.restore(path, live)
    live.dispose()

    assert current_revision(db_path) == head_revision()
    engine = make_engine(db_path)
    with engine.connect() as conn:
        assert conn.execute(select(Customer)).all() == []
    engine.dispose()
    assert path.exists()  # the backup file itself is untouched
