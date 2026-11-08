"""The single home for money and percentage rounding (Constitution, Principle II).

Money is stored as integer minor units (pence) and percentages as integer basis points
(20% = 2000). Application code only ever sees ``Decimal``. Floats are rejected everywhere.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MONEY_PLACES = Decimal("0.01")
PERCENT_PLACES = Decimal("0.01")
ROUNDING = ROUND_HALF_UP


def _require_decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal | int):
        raise TypeError(f"Expected Decimal or int, got {type(value).__name__}")
    return Decimal(value)


def _require_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Expected int, got {type(value).__name__}")
    return value


def round_money(value: Decimal) -> Decimal:
    return _require_decimal(value).quantize(MONEY_PLACES, rounding=ROUNDING)


def to_minor_units(value: Decimal) -> int:
    return int(round_money(value) * 100)


def from_minor_units(value: int) -> Decimal:
    return (Decimal(_require_int(value)) / 100).quantize(MONEY_PLACES)


def percent_to_bp(value: Decimal) -> int:
    """``Decimal("17.5")`` -> ``1750``. More than two decimal places is an error."""
    dec = _require_decimal(value)
    if dec != dec.quantize(PERCENT_PLACES):
        raise ValueError("Percentages may have at most two decimal places")
    return int(dec * 100)


def bp_to_percent(value: int) -> Decimal:
    return (Decimal(_require_int(value)) / 100).quantize(PERCENT_PLACES)
