"""Pure validation and normalisation rules (research.md §6). No database or web imports."""

from __future__ import annotations

import re

from email_validator import EmailNotValidError
from email_validator import validate_email as _validate_email

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
