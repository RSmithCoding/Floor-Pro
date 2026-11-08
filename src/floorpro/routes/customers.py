"""Customer routes (contracts/routes.md)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from floorpro.db import get_session
from floorpro.domain.validation import looks_like_phone
from floorpro.models import Customer
from floorpro.schemas.customer_form import from_form
from floorpro.services import customer_service
from floorpro.templating import flash_redirect, is_htmx, render

router = APIRouter(prefix="/customers")

EMPTY_FORM = {
    "title": "",
    "first_name": "",
    "last_name": "",
    "company_name": "",
    "mobile_phone": "",
    "other_phone": "",
    "email": "",
    "address_line1": "",
    "address_line2": "",
    "town": "",
    "county": "",
    "postcode": "",
    "notes": "",
    "marketing_consent": False,
    "customer_type": "domestic",
    "show_vat_breakdown": False,
}


def _values_from_submission(data) -> dict:
    values = {key: data.get(key, "") for key in EMPTY_FORM if isinstance(EMPTY_FORM[key], str)}
    values["marketing_consent"] = data.get("marketing_consent") == "on"
    values["show_vat_breakdown"] = data.get("show_vat_breakdown") == "on"
    values["customer_type"] = data.get("customer_type") or "domestic"
    return values


def _prefill_values(prefill: str) -> dict:
    values = dict(EMPTY_FORM)
    text = prefill.strip()
    if not text:
        return values
    if "@" in text:
        values["email"] = text
    elif looks_like_phone(text):
        values["mobile_phone"] = text
    else:
        first, _, rest = text.partition(" ")
        values["first_name"] = first
        values["last_name"] = rest.strip()
    return values


def _form_page(request: Request, values: dict, *, errors=None, duplicates=None, status=200):
    context = {
        "nav": "customers",
        "values": values,
        "errors": errors or {},
        "duplicates": duplicates or [],
        "customer": None,
    }
    return render(
        request,
        "customers/form.html",
        "customers/_form.html",
        context,
        status_code=status,
    )


def _get_or_404(session: Session, customer_id: int) -> Customer:
    customer = customer_service.get(session, customer_id)
    if customer is None:
        raise HTTPException(status_code=404)
    return customer


@router.get("")
def list_customers(
    request: Request,
    q: str = "",
    type: str = "all",
    archived: str = "0",
    sort: str = "name",
    dir: str = "asc",
    session: Session = Depends(get_session),
):
    customer_type = type if type in customer_service.TYPES else "all"
    sort = sort if sort in customer_service.SORTS else "name"
    direction = "desc" if dir == "desc" else "asc"
    show_archived = archived == "1"
    result = customer_service.search(session, q, customer_type, show_archived, sort, direction)
    params = {"q": q, "type": customer_type, "archived": "1" if show_archived else "0"}
    context = {
        "nav": "customers",
        "result": result,
        "q": q,
        "customer_type": customer_type,
        "archived": show_archived,
        "sort": sort,
        "direction": direction,
        "params": params,
    }
    return render(request, "customers/index.html", "customers/_results.html", context)


@router.get("/new")
def new_customer(request: Request, prefill: str = ""):
    return _form_page(request, _prefill_values(prefill))


@router.post("")
async def create_customer(request: Request, session: Session = Depends(get_session)):
    data = await request.form()
    values = _values_from_submission(data)
    form, errors = from_form(data)
    if form is None:
        return _form_page(request, values, errors=errors, status=422)

    if data.get("confirm_duplicate") != "1":
        duplicates = customer_service.find_duplicates(session, form.phones, form.email)
        if duplicates:
            return _form_page(request, values, duplicates=duplicates)

    customer, warnings = customer_service.create(session, form)
    session.commit()
    toasts = [("success", f"Customer {customer.reference} added")]
    toasts += [("warning", w) for w in warnings]
    url = f"/customers/{customer.id}"
    if is_htmx(request):
        return render(
            request,
            "customers/detail.html",
            context={"nav": "customers", "customer": customer},
            toast=toasts,
            push_url=url,
        )
    message = " ".join(m for _, m in toasts)
    return flash_redirect(url, "warning" if warnings else "success", message)


@router.get("/{customer_id}")
def customer_detail(request: Request, customer_id: int, session: Session = Depends(get_session)):
    customer = _get_or_404(session, customer_id)
    return render(
        request, "customers/detail.html", context={"nav": "customers", "customer": customer}
    )
