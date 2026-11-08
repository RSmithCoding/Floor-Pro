"""Pure customer rules: references, names, VAT-breakdown preference."""

from __future__ import annotations

import re

_REFERENCE_RE = re.compile(r"^c-?0*(\d+)$", re.IGNORECASE)


def format_reference(customer_id: int | None) -> str:
    """``42`` -> ``"C-00042"``. Grows past five digits naturally."""
    return "" if customer_id is None else f"C-{customer_id:05d}"


def parse_reference(text: str) -> int | None:
    """``"C-00042"``, ``"c42"`` or ``"C42"`` -> ``42``; anything else -> ``None``."""
    match = _REFERENCE_RE.match(text.strip())
    if not match:
        return None
    number = int(match.group(1))
    return number or None


def person_name(first: str | None, last: str | None) -> str:
    return " ".join(part for part in (first, last) if part)


def display_name(first: str | None, last: str | None, company: str | None) -> str:
    """``"Jane Smith"``, ``"Acme Flooring"``, or ``"Acme Flooring (Jane Smith)"``."""
    person = person_name(first, last)
    if company and person:
        return f"{company} ({person})"
    return company or person


def sort_name(first: str | None, last: str | None, company: str | None) -> str:
    """``"Smith, Jane"`` for people; the company name when there's no last name."""
    if last:
        return f"{last}, {first}" if first else last
    return company or first or ""


def resolve_vat_breakdown(
    old_type: str | None, new_type: str, requested: bool | None, previous: bool = False
) -> bool:
    """The "show VAT breakdown" rule (data-model.md, FR-026/FR-027).

    Trade customers always get a breakdown. For domestic customers an explicit choice wins;
    with no choice, a former trade customer keeps it on, otherwise the previous value stays
    (``False`` for a new customer).
    """
    if new_type == "trade":
        return True
    if requested is not None:
        return requested
    if old_type == "trade":
        return True
    return previous
