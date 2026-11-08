"""Business settings: defaults, reading, and (in US2) validated, confirmed changes."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from floorpro.models import BusinessSettings, PriceEntryMode
from floorpro.models.base import utcnow

DEFAULTS = {
    "currency_code": "GBP",
    "vat_registered": True,
    "vat_rate": Decimal("20.00"),
    "vat_number": None,
    "price_entry_mode": PriceEntryMode.INC_VAT.value,
}


def get_settings(session: Session) -> BusinessSettings | None:
    return session.get(BusinessSettings, 1)


def ensure_settings(session: Session) -> tuple[BusinessSettings, bool]:
    """Return the single settings row, creating it with the defaults if it's missing."""
    settings = get_settings(session)
    if settings is not None:
        return settings, False
    settings = BusinessSettings(id=1, updated_at=utcnow(), **DEFAULTS)
    session.add(settings)
    session.flush()
    return settings, True
