"""Pure validation and normalisation rules (research.md §6). No database or web imports."""

from __future__ import annotations

import re
from decimal import Decimal

from email_validator import EmailNotValidError
from email_validator import validate_email as _validate_email

from floorpro.domain.money import PERCENT_PLACES

_POSTCODE_RE = re.compile(r"^(GIR 0AA|[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2})$")
_PHONE_CHARS_RE = re.compile(r"^[\d\s()+\-.]+$")

MIN_PHONE_DIGITS = 7
PHONE_ERROR = "Enter a phone number with at least 7 digits."
EMAIL_ERROR = "Enter a valid email address, for example name@example.com."


# --- Postcodes -----------------------------------------------------------------------------


def postcode_compact(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def normalise_postcode(value: str) -> tuple[str, bool]:
    """Return ``(postcode, warning)``. Recognised UK postcodes come back as ``"SW1A 1AA"``.

    Anything unrecognised is returned upper-cased with ``warning=True``; it's still saved,
    so unusual addresses can be recorded (spec edge case).
    """
    compact = postcode_compact(value)
    candidate = f"{compact[:-3]} {compact[-3:]}" if len(compact) >= 5 else compact
    if _POSTCODE_RE.match(candidate):
        return candidate, False
    return " ".join(value.split()).upper(), True


# --- Phone numbers -------------------------------------------------------------------------


def looks_like_phone(value: str) -> bool:
    return bool(_PHONE_CHARS_RE.match(value.strip())) and len(re.sub(r"\D", "", value)) >= 3


def phone_digits(value: str) -> str:
    """Digits only, with a UK international prefix (+44 / 0044) turned into a leading 0."""
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+44") or digits.startswith("0044"):
        rest = digits[2:] if raw.startswith("+") else digits[4:]
        return rest if rest.startswith("0") else f"0{rest}"
    return digits


def validate_phone(value: str) -> str | None:
    return None if len(phone_digits(value)) >= MIN_PHONE_DIGITS else PHONE_ERROR


# --- Email ---------------------------------------------------------------------------------


def validate_email(value: str) -> str | None:
    """Format check only. DNS deliverability checks are off: FloorPro works offline."""
    try:
        _validate_email(value, check_deliverability=False)
    except EmailNotValidError:
        return EMAIL_ERROR
    return None


# --- VAT -----------------------------------------------------------------------------------

VAT_RATE_ERROR = "Enter a VAT rate between 0 and 100, with up to two decimal places."
VAT_NUMBER_ERROR = "Enter a UK VAT number, for example GB123456789."
_VAT_RATE_RE = re.compile(r"^\d{1,3}(\.\d{1,2})?$")
_VAT_NUMBER_RE = re.compile(r"^GB(\d{9}|\d{12}|GD\d{3}|HA\d{3})$")


def validate_vat_rate(value: str) -> Decimal:
    """``"17.5"`` -> ``Decimal("17.50")``. Raises ``ValueError(VAT_RATE_ERROR)``."""
    text = value.strip()
    if not _VAT_RATE_RE.match(text):
        raise ValueError(VAT_RATE_ERROR)
    rate = Decimal(text)
    if not Decimal(0) <= rate <= Decimal(100):
        raise ValueError(VAT_RATE_ERROR)
    return rate.quantize(PERCENT_PLACES)


def normalise_vat_number(value: str) -> str:
    """``"gb 123 4567 89"`` -> ``"GB123456789"``. Raises ``ValueError(VAT_NUMBER_ERROR)``."""
    compact = re.sub(r"\s+", "", value).upper()
    if not _VAT_NUMBER_RE.match(compact):
        raise ValueError(VAT_NUMBER_ERROR)
    return compact
