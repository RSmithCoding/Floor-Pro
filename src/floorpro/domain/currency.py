"""Supported currencies and money formatting. FloorPro never converts between currencies."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from floorpro.domain.money import round_money


@dataclass(frozen=True)
class Currency:
    code: str
    symbol: str
    name: str


SUPPORTED_CURRENCIES: dict[str, Currency] = {
    c.code: c
    for c in (
        Currency("GBP", "£", "Pound sterling"),
        Currency("EUR", "€", "Euro"),
        Currency("USD", "$", "US dollar"),
    )
}

DEFAULT_CURRENCY = "GBP"


def get_currency(code: str) -> Currency:
    try:
        return SUPPORTED_CURRENCIES[code]
    except KeyError:
        raise ValueError(f"Unsupported currency: {code}") from None


def format_money(value: Decimal, code: str) -> str:
    """``format_money(Decimal("1234.5"), "GBP")`` -> ``"£1,234.50"`` (always 2 dp)."""
    amount = round_money(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}{get_currency(code).symbol}{abs(amount):,.2f}"
