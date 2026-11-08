"""Business settings: defaults, validated and confirmed changes, and change history."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from floorpro.domain import settings_history
from floorpro.domain.currency import get_currency
from floorpro.domain.settings_history import (
    DEFAULT_SNAPSHOT,
    FIELDS,
    SettingsSnapshot,
    canonical,
    snapshot_of,
)
from floorpro.models import BusinessSettings, SettingsChange
from floorpro.models.base import utcnow
from floorpro.paths import secret_key
from floorpro.schemas.settings_form import SettingsForm

FIELD_LABELS = {
    "currency_code": "Currency",
    "vat_registered": "VAT registered",
    "vat_rate": "VAT rate",
    "vat_number": "VAT number",
    "price_entry_mode": "Price entry mode",
}
MODE_LABELS = {"inc_vat": "Prices include VAT", "ex_vat": "Prices exclude VAT"}


def get_settings(session: Session) -> BusinessSettings | None:
    return session.get(BusinessSettings, 1)


def ensure_settings(session: Session) -> tuple[BusinessSettings, bool]:
    """Return the single settings row, creating it with the defaults if it's missing."""
    settings = get_settings(session)
    if settings is not None:
        return settings, False
    defaults = {field: getattr(DEFAULT_SNAPSHOT, field) for field in FIELDS}
    settings = BusinessSettings(id=1, updated_at=utcnow(), **defaults)
    session.add(settings)
    session.flush()
    return settings, True


# --- Display -------------------------------------------------------------------------------


def display_value(field: str, value: str | None) -> str:
    """Human-readable form of a canonical value, e.g. ``"17.50"`` -> ``"17.5%"``."""
    if value is None or value == "":
        return "None"
    if field == "vat_rate":
        return f"{value.rstrip('0').rstrip('.')}%"
    if field == "vat_registered":
        return "Yes" if value == "true" else "No"
    if field == "currency_code":
        try:
            return f"{value} ({get_currency(value).symbol})"
        except ValueError:
            return value
    if field == "price_entry_mode":
        return MODE_LABELS.get(value, value)
    return value


@dataclass(frozen=True)
class FieldChange:
    field: str
    old: str | None
    new: str | None

    @property
    def label(self) -> str:
        return FIELD_LABELS[self.field]

    @property
    def old_display(self) -> str:
        return display_value(self.field, self.old)

    @property
    def new_display(self) -> str:
        return display_value(self.field, self.new)


# --- Changes -------------------------------------------------------------------------------


def diff(current: SettingsSnapshot, form: SettingsForm) -> list[FieldChange]:
    staged = form.snapshot()
    result = []
    for field in FIELDS:
        old = canonical(field, getattr(current, field))
        new = canonical(field, getattr(staged, field))
        if old != new:
            result.append(FieldChange(field, old, new))
    return result


def _token_payload(form: SettingsForm, settings: BusinessSettings) -> bytes:
    staged = form.snapshot()
    parts = [f"{f}={canonical(f, getattr(staged, f))}" for f in FIELDS]
    parts.append(f"updated_at={settings.updated_at.isoformat()}")
    return "|".join(parts).encode()


def make_token(form: SettingsForm, settings: BusinessSettings) -> str:
    return hmac.new(secret_key(), _token_payload(form, settings), hashlib.sha256).hexdigest()


def verify_token(token: str, form: SettingsForm, settings: BusinessSettings) -> bool:
    """False if the staged values were altered or the settings changed since staging."""
    return hmac.compare_digest(token or "", make_token(form, settings))


def apply(session: Session, form: SettingsForm) -> list[FieldChange]:
    """Save the form and record one history row per changed field, in one transaction."""
    settings, _ = ensure_settings(session)
    changes = diff(snapshot_of(settings), form)
    if not changes:
        return []
    now = utcnow()
    change_set_id = str(uuid.uuid4())
    for field in FIELDS:
        setattr(settings, field, getattr(form, field))
    settings.updated_at = now
    for change in changes:
        session.add(
            SettingsChange(
                change_set_id=change_set_id,
                changed_at=now,
                field=change.field,
                old_value=change.old,
                new_value=change.new,
            )
        )
    session.flush()
    return changes


# --- History -------------------------------------------------------------------------------


@dataclass
class HistoryPage:
    rows: list[SettingsChange]
    page: int
    per_page: int
    total: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.per_page))


def history(session: Session, page: int = 1, per_page: int = 25) -> HistoryPage:
    page = max(1, page)
    total = session.scalar(select(func.count()).select_from(SettingsChange)) or 0
    rows = session.scalars(
        select(SettingsChange)
        .order_by(SettingsChange.changed_at.desc(), SettingsChange.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return HistoryPage(list(rows), page, per_page, total)


def settings_at(session: Session, when: datetime) -> SettingsSnapshot:
    changes = session.scalars(select(SettingsChange).where(SettingsChange.changed_at <= when))
    return settings_history.settings_at(DEFAULT_SNAPSHOT, list(changes), when)
