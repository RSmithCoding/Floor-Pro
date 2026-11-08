"""Build tests/fixtures/backup-v1.fpbackup, the committed cross-platform fixture (SC-006).

Run once and commit the result. It must never be regenerated in a way that changes the
format; it refuses to overwrite an existing fixture unless --force is given.

Usage:
    uv run python scripts/make_backup_fixture.py [--force]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "backup-v1.fpbackup"
PASSWORD = "correct horse battery"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="overwrite an existing fixture")
    args = parser.parse_args(argv)
    if FIXTURE.exists() and not args.force:
        print(f"{FIXTURE.relative_to(ROOT)} already exists (use --force).", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["FLOORPRO_DATA_DIR"] = tmp
        from floorpro import backup_file, paths
        from floorpro.db import make_engine, make_sessionmaker
        from floorpro.domain.backups import BackupKind
        from floorpro.migrate import upgrade_to_head
        from floorpro.schemas.customer_form import CustomerForm
        from floorpro.schemas.settings_form import SettingsForm
        from floorpro.services import backup_service, customer_service, settings_service

        db_path = paths.db_path()
        upgrade_to_head(db_path)
        engine = make_engine(db_path)
        with make_sessionmaker(engine).begin() as session:
            settings_service.ensure_settings(session)
            settings_service.apply(
                session,
                SettingsForm(
                    currency_code="GBP",
                    vat_registered=True,
                    vat_rate=Decimal("17.5"),
                    vat_number=None,
                    price_entry_mode="inc_vat",
                ),
            )
            customer_service.create(
                session,
                CustomerForm(
                    first_name="Ada",
                    last_name="Lovelace",
                    mobile_phone="07700 900001",
                    postcode="SW1A 1AA",
                ),
            )
            customer_service.create(
                session,
                CustomerForm(
                    company_name="Brunel Flooring Ltd",
                    customer_type="trade",
                    other_phone="0117 496 0002",
                ),
            )
            archived, _ = customer_service.create(
                session,
                CustomerForm(
                    first_name="Charles", last_name="Babbage", mobile_phone="07700 900003"
                ),
            )
            customer_service.archive(session, archived)
        engine.dispose()

        kdf = replace(backup_file.KdfParams(n=1024, r=8, p=1), salt=os.urandom(16))
        key = backup_file.derive_key(PASSWORD, kdf)
        stored = backup_service.StoredKey(kdf, key, backup_file.key_id(key), backup_service.now())
        data, revision, customers = backup_service.snapshot(db_path)
        written = backup_service.write_protected(
            BackupKind.MANUAL, data, revision, customers, Path(tmp), stored
        )
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_bytes(written.read_bytes())
    print(f"Wrote {FIXTURE.relative_to(ROOT)} (revision {revision}, {customers} customers)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
