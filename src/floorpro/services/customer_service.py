"""Customer business logic.

US1: create, search, duplicates. US3: update, archive, export, erase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC

from sqlalchemy import Select, func, literal, or_, select
from sqlalchemy.orm import Session

from floorpro.domain.customers import parse_reference, person_name
from floorpro.domain.validation import (
    looks_like_phone,
    normalise_postcode,
    phone_digits,
    postcode_compact,
)
from floorpro.models import Customer
from floorpro.models.base import utcnow
from floorpro.schemas.customer_form import TEXT_FIELDS, CustomerForm

SEARCH_LIMIT = 50
SORTS = ("name", "reference", "created")
TYPES = ("all", "domestic", "trade")


def postcode_warning(postcode: str) -> str:
    return f"The postcode “{postcode}” doesn't look like a UK postcode. Please check it."


def _apply_form(customer: Customer, form: CustomerForm) -> list[str]:
    """Copy form values onto the customer, computing derived columns. Returns warnings."""
    warnings: list[str] = []
    for field in TEXT_FIELDS:
        setattr(customer, field, getattr(form, field))
    customer.marketing_consent = form.marketing_consent
    customer.customer_type = form.customer_type
    # Minimal guard so the database rule always holds; the full rules arrive with US4.
    customer.show_vat_breakdown = form.show_vat_breakdown or form.customer_type == "trade"

    customer.mobile_phone_digits = phone_digits(form.mobile_phone) if form.mobile_phone else None
    customer.other_phone_digits = phone_digits(form.other_phone) if form.other_phone else None
    if form.postcode:
        customer.postcode, warn = normalise_postcode(form.postcode)
        customer.postcode_compact = postcode_compact(customer.postcode)
        if warn:
            warnings.append(postcode_warning(customer.postcode))
    else:
        customer.postcode = customer.postcode_compact = None
    customer.updated_at = utcnow()
    return warnings


def create(session: Session, form: CustomerForm) -> tuple[Customer, list[str]]:
    customer = Customer(created_at=utcnow())
    warnings = _apply_form(customer, form)
    session.add(customer)
    session.flush()  # assigns id, and therefore reference
    return customer, warnings


def get(session: Session, customer_id: int) -> Customer | None:
    return session.get(Customer, customer_id)


def find_duplicates(
    session: Session, phones: list[str], email: str | None, exclude_id: int | None = None
) -> list[Customer]:
    """Active or archived customers sharing a phone number (any spacing) or email (any case)."""
    conditions = []
    for digits in {phone_digits(p) for p in phones if p}:
        conditions += [
            Customer.mobile_phone_digits == digits,
            Customer.other_phone_digits == digits,
        ]
    if email:
        conditions.append(func.lower(Customer.email) == email.lower())
    if not conditions:
        return []
    stmt = select(Customer).where(or_(*conditions)).order_by(Customer.id)
    if exclude_id is not None:
        stmt = stmt.where(Customer.id != exclude_id)
    return list(session.scalars(stmt))


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_filter(q: str):
    like = f"%{_escape_like(q)}%"
    full_name = (
        func.coalesce(Customer.first_name, "")
        + literal(" ")
        + func.coalesce(Customer.last_name, "")
    )
    conditions = [
        Customer.first_name.like(like, escape="\\"),
        Customer.last_name.like(like, escape="\\"),
        Customer.company_name.like(like, escape="\\"),
        Customer.email.like(like, escape="\\"),
        full_name.like(like, escape="\\"),
    ]
    if looks_like_phone(q):
        digits = f"%{phone_digits(q)}%"
        conditions += [
            Customer.mobile_phone_digits.like(digits),
            Customer.other_phone_digits.like(digits),
        ]
    compact = postcode_compact(q)
    if compact.isalnum():
        conditions.append(Customer.postcode_compact.like(f"%{compact}%"))
    if (ref := parse_reference(q)) is not None:
        conditions.append(Customer.id == ref)
    return or_(*conditions)


@dataclass
class SearchResult:
    customers: list[Customer]
    total: int


def search(
    session: Session,
    q: str = "",
    customer_type: str = "all",
    archived: bool = False,
    sort: str = "name",
    direction: str = "asc",
    limit: int = SEARCH_LIMIT,
) -> SearchResult:
    stmt: Select = select(Customer)
    if not archived:
        stmt = stmt.where(Customer.is_archived.is_(False))
    if customer_type in ("domestic", "trade"):
        stmt = stmt.where(Customer.customer_type == customer_type)
    if q := q.strip():
        stmt = stmt.where(_search_filter(q))

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    desc = direction == "desc"
    if sort == "reference":
        order = [Customer.id.desc() if desc else Customer.id]
    elif sort == "created":
        order = [
            Customer.created_at.desc() if desc else Customer.created_at,
            Customer.id.desc() if desc else Customer.id,
        ]
    else:
        primary = func.coalesce(
            Customer.last_name, Customer.company_name, Customer.first_name
        ).collate("NOCASE")
        secondary = func.coalesce(Customer.first_name, "").collate("NOCASE")
        order = [primary.desc(), secondary.desc()] if desc else [primary, secondary]
    customers = list(session.scalars(stmt.order_by(*order).limit(limit)))
    return SearchResult(customers, total)


# --- US3: update, archive, export, erase ---------------------------------------------------


def update(session: Session, customer: Customer, form: CustomerForm) -> list[str]:
    warnings = _apply_form(customer, form)
    session.flush()
    return warnings


def phones_or_email_changed(customer: Customer, form: CustomerForm) -> bool:
    old_phones = {d for d in (customer.mobile_phone_digits, customer.other_phone_digits) if d}
    new_phones = {phone_digits(p) for p in form.phones}
    old_email = (customer.email or "").lower()
    new_email = (form.email or "").lower()
    return bool(new_phones - old_phones) or (new_email != old_email and bool(new_email))


def archive(session: Session, customer: Customer) -> None:
    customer.is_archived = True
    customer.archived_at = utcnow()
    customer.updated_at = customer.archived_at
    session.flush()


def restore(session: Session, customer: Customer) -> None:
    customer.is_archived = False
    customer.archived_at = None
    customer.updated_at = utcnow()
    session.flush()


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def export_dict(customer: Customer) -> dict:
    """Everything FloorPro holds about one customer (contracts/customer-export.md, v1)."""
    return {
        "export": {
            "format_version": 1,
            "produced_by": "FloorPro",
            "exported_at": _iso(utcnow()),
            "description": "All personal data FloorPro holds about this customer.",
        },
        "customer": {
            "reference": customer.reference,
            "customer_type": customer.customer_type,
            "show_vat_breakdown": customer.show_vat_breakdown,
            "title": customer.title,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "company_name": customer.company_name,
            "mobile_phone": customer.mobile_phone,
            "other_phone": customer.other_phone,
            "email": customer.email,
            "address": {
                "line_1": customer.address_line1,
                "line_2": customer.address_line2,
                "town": customer.town,
                "county": customer.county,
                "postcode": customer.postcode,
            },
            "notes": customer.notes,
            "marketing_consent": customer.marketing_consent,
            "archived": customer.is_archived,
            "archived_at": _iso(customer.archived_at),
            "created_at": _iso(customer.created_at),
            "updated_at": _iso(customer.updated_at),
        },
        "related_records": {"jobs": [], "orders": [], "appointments": [], "invoices": []},
    }


def has_linked_records(session: Session, customer: Customer) -> bool:
    """Whether jobs, orders, appointments or invoices refer to this customer.

    Always False for now: no such records exist yet. The first feature that adds them must
    extend this check and implement the anonymise path in ``erase`` (research.md §12).
    """
    return False


def _name_matches(customer: Customer, typed: str) -> bool:
    wanted = " ".join(typed.split()).casefold()
    if not wanted:
        return False
    candidates = {
        customer.display_name,
        customer.company_name or "",
        person_name(customer.first_name, customer.last_name),
    }
    return wanted in {" ".join(c.split()).casefold() for c in candidates if c}


def erase(session: Session, customer: Customer, confirm_name: str) -> bool:
    """Permanently erase a customer once their name (person or company) is typed to confirm."""
    if not _name_matches(customer, confirm_name):
        return False
    if has_linked_records(session, customer):
        raise NotImplementedError("anonymise — implemented with first linked-records feature")
    session.delete(customer)
    session.flush()
    return True
