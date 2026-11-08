"""Customer business logic: create, find duplicates, search (US1)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, literal, or_, select
from sqlalchemy.orm import Session

from floorpro.domain.customers import parse_reference
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
