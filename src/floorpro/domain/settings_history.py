"""Settings snapshots and the "which settings were in force at time T" rule (FR-007).

History rows store values in a canonical string form, e.g. ``"20.00"``, ``"true"``,
``"GBP"``. Pure functions only: no database or web imports.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from floorpro.domain.money import PERCENT_PLACES

FIELDS = ("currency_code", "vat_registered", "vat_rate", "vat_number", "price_entry_mode")


@dataclass(frozen=True)
class SettingsSnapshot:
    currency_code: str
    vat_registered: bool
    vat_rate: Decimal
    vat_number: str | None
    price_entry_mode: str


DEFAULT_SNAPSHOT = SettingsSnapshot(
    currency_code="GBP",
    vat_registered=True,
    vat_rate=Decimal("20.00"),
    vat_number=None,
    price_entry_mode="inc_vat",
)


class ChangeLike(Protocol):
    changed_at: datetime
    field: str
    new_value: str | None


def canonical(field: str, value: Any) -> str | None:
    if value is None:
        return None
    if field == "vat_rate":
        return str(Decimal(value).quantize(PERCENT_PLACES))
    if field == "vat_registered":
        return "true" if value else "false"
    return str(value)


def parse_canonical(field: str, value: str | None) -> Any:
    if field == "vat_rate":
        return Decimal(value) if value is not None else None
    if field == "vat_registered":
        return value == "true"
    return value


def snapshot_of(obj: Any) -> SettingsSnapshot:
    """Snapshot of any object with the five settings attributes (e.g. the settings row)."""
    return SettingsSnapshot(**{field: getattr(obj, field) for field in FIELDS})


def settings_at(
    defaults: SettingsSnapshot, changes: Iterable[ChangeLike], when: datetime
) -> SettingsSnapshot:
    """Start from the defaults and apply every change made at or before ``when``, in order."""
    snapshot = defaults
    for change in sorted(changes, key=lambda c: c.changed_at):
        if change.changed_at > when:
            break
        value = parse_canonical(change.field, change.new_value)
        snapshot = replace(snapshot, **{change.field: value})
    return snapshot
