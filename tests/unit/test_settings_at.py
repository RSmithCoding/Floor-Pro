from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from floorpro.domain.settings_history import DEFAULT_SNAPSHOT, canonical, settings_at

T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


@dataclass
class Change:
    change_set_id: str
    changed_at: datetime
    field: str
    old_value: str | None
    new_value: str | None


def test_defaults():
    assert DEFAULT_SNAPSHOT.currency_code == "GBP"
    assert DEFAULT_SNAPSHOT.vat_registered is True
    assert DEFAULT_SNAPSHOT.vat_rate == Decimal("20.00")
    assert DEFAULT_SNAPSHOT.vat_number is None
    assert DEFAULT_SNAPSHOT.price_entry_mode == "inc_vat"


def test_no_changes_returns_defaults():
    assert settings_at(DEFAULT_SNAPSHOT, [], T0) == DEFAULT_SNAPSHOT


def test_changes_applied_in_order_up_to_and_including_when():
    changes = [
        Change("b", T0 + timedelta(days=2), "vat_rate", "17.50", "15.00"),
        Change("a", T0 + timedelta(days=1), "vat_rate", "20.00", "17.50"),
        Change("c", T0 + timedelta(days=3), "vat_rate", "15.00", "20.00"),
    ]
    assert settings_at(DEFAULT_SNAPSHOT, changes, T0).vat_rate == Decimal("20.00")
    assert settings_at(DEFAULT_SNAPSHOT, changes, T0 + timedelta(days=1)).vat_rate == Decimal(
        "17.50"
    )
    assert settings_at(DEFAULT_SNAPSHOT, changes, T0 + timedelta(days=2, hours=5)).vat_rate == (
        Decimal("15.00")
    )
    assert settings_at(DEFAULT_SNAPSHOT, changes, T0 + timedelta(days=9)).vat_rate == Decimal(
        "20.00"
    )


def test_change_set_fields_applied_together():
    when = T0 + timedelta(hours=1)
    changes = [
        Change("x", when, "currency_code", "GBP", "EUR"),
        Change("x", when, "vat_registered", "true", "false"),
        Change("x", when, "vat_number", None, "GB123456789"),
        Change("x", when, "price_entry_mode", "inc_vat", "ex_vat"),
    ]
    expected = replace(
        DEFAULT_SNAPSHOT,
        currency_code="EUR",
        vat_registered=False,
        vat_number="GB123456789",
        price_entry_mode="ex_vat",
    )
    assert settings_at(DEFAULT_SNAPSHOT, changes, T0) == DEFAULT_SNAPSHOT
    assert settings_at(DEFAULT_SNAPSHOT, changes, when) == expected


def test_canonical():
    assert canonical("vat_rate", Decimal("20")) == "20.00"
    assert canonical("vat_rate", Decimal("17.5")) == "17.50"
    assert canonical("vat_registered", True) == "true"
    assert canonical("vat_registered", False) == "false"
    assert canonical("currency_code", "GBP") == "GBP"
    assert canonical("price_entry_mode", "ex_vat") == "ex_vat"
    assert canonical("vat_number", None) is None
