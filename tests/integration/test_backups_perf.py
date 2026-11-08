"""SC-001 / SC-002: backing up and restoring 10,000 customers stays fast."""

from __future__ import annotations

import time

import pytest

from tests.integration.backup_helpers import only_backup


def seed_10k(client, app):
    """10,000 realistic customers, inserted in one statement."""
    import random
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import insert

    from floorpro.models import Customer

    rng = random.Random(7)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(10_000):
        phone = f"07{rng.randrange(100_000_000, 999_999_999)}"
        rows.append(
            dict(
                customer_type="domestic",
                show_vat_breakdown=False,
                first_name=f"First{i}",
                last_name=f"Last{i}",
                mobile_phone=phone,
                mobile_phone_digits=phone,
                email=f"customer{i}@example.com",
                address_line1=f"{i} Long Street Name",
                notes="Prefers morning fittings. " * 3,
                marketing_consent=False,
                is_archived=False,
                created_at=start + timedelta(minutes=i),
                updated_at=start + timedelta(minutes=i),
            )
        )
    with app.state.sessionmaker.begin() as session:
        session.execute(insert(Customer), rows)


@pytest.mark.slow
def test_backup_and_restore_10k_customers(client, app, backup_password, data_dir):
    seed_10k(client, app)

    began = time.perf_counter()
    response = client.post("/backups")
    backup_seconds = time.perf_counter() - began
    assert "Backup made · 10,000 customers" in response.text
    assert backup_seconds < 10, f"backup took {backup_seconds:.1f} s"

    path = only_backup(data_dir)
    began = time.perf_counter()
    response = client.post(f"/backups/local/{path.name}/restore", data={"confirm": "RESTORE"})
    restore_seconds = time.perf_counter() - began
    assert response.status_code == 200
    assert restore_seconds < 30, f"restore took {restore_seconds:.1f} s"


@pytest.mark.slow
def test_backups_page_with_40_backups(client, backup_password, data_dir):
    for _ in range(40):
        client.post("/backups")
    client.get("/backups")
    began = time.perf_counter()
    response = client.get("/backups")
    elapsed = time.perf_counter() - began
    assert response.status_code == 200
    assert elapsed < 0.3, f"/backups took {elapsed * 1000:.0f} ms"
