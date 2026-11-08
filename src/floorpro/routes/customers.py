"""Customer routes (contracts/routes.md)."""

from __future__ import annotations

import json
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from floorpro.db import get_session
from floorpro.domain.customers import resolve_vat_breakdown
from floorpro.domain.validation import looks_like_phone
from floorpro.models import Customer
from floorpro.schemas.customer_form import from_form
from floorpro.services import customer_service
from floorpro.templating import Toast, flash_redirect, is_htmx, render

router = APIRouter(prefix="/customers")
log = logging.getLogger(__name__)

DIALOG_ERROR_HEADERS = {"HX-Retarget": "#modal", "HX-Reswap": "innerHTML"}

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
TEXT_KEYS = [key for key, value in EMPTY_FORM.items() if isinstance(value, str)]


# --- Helpers -------------------------------------------------------------------------------


def _values_from_submission(data) -> dict:
    values = {key: data.get(key, "") for key in TEXT_KEYS}
    values["marketing_consent"] = data.get("marketing_consent") == "on"
    values["show_vat_breakdown"] = data.get("show_vat_breakdown") == "on"
    values["customer_type"] = data.get("customer_type") or "domestic"
    return values


def _values_from_customer(customer: Customer) -> dict:
    values = {key: getattr(customer, key) or "" for key in TEXT_KEYS}
    values["marketing_consent"] = customer.marketing_consent
    values["show_vat_breakdown"] = customer.show_vat_breakdown
    values["customer_type"] = customer.customer_type
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


def _form_page(
    request: Request,
    values: dict,
    *,
    customer: Customer | None = None,
    errors=None,
    duplicates=None,
    status=200,
):
    context = {
        "nav": "customers",
        "values": values,
        "errors": errors or {},
        "duplicates": duplicates or [],
        "customer": customer,
    }
    return render(
        request, "customers/form.html", "customers/_form.html", context, status_code=status
    )


def _get_or_404(session: Session, customer_id: int) -> Customer:
    customer = customer_service.get(session, customer_id)
    if customer is None:
        raise HTTPException(status_code=404)
    return customer


def _detail_context(customer: Customer, **extra) -> dict:
    return {"nav": "customers", "customer": customer, **extra}


def _list_context(
    session: Session,
    q: str = "",
    customer_type: str = "all",
    archived: bool = False,
    sort: str = "name",
    direction: str = "asc",
) -> dict:
    result = customer_service.search(session, q, customer_type, archived, sort, direction)
    return {
        "nav": "customers",
        "result": result,
        "q": q,
        "customer_type": customer_type,
        "archived": archived,
        "sort": sort,
        "direction": direction,
        "params": {"q": q, "type": customer_type, "archived": "1" if archived else "0"},
    }


def _after_write(request: Request, url: str, page: str, context: dict, toasts: list[Toast]):
    """Success after a write (research.md §15): render the destination for HTMX requests,
    otherwise redirect with a one-time flash message."""
    if is_htmx(request):
        return render(request, page, context=context, toast=toasts, push_url=url)
    kind = "warning" if any(k == "warning" for k, _ in toasts) else toasts[0][0]
    return flash_redirect(url, kind, " ".join(message for _, message in toasts))


# --- List, add, view -----------------------------------------------------------------------


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
    context = _list_context(
        session,
        q,
        type if type in customer_service.TYPES else "all",
        archived == "1",
        sort if sort in customer_service.SORTS else "name",
        "desc" if dir == "desc" else "asc",
    )
    return render(request, "customers/index.html", "customers/_results.html", context)


@router.get("/new")
def new_customer(request: Request, prefill: str = "", customer_type: str = "domestic"):
    values = _prefill_values(prefill)
    if customer_type == "trade":
        values["customer_type"] = "trade"
        values["show_vat_breakdown"] = True
    return _form_page(request, values)


@router.get("/form/vat-fields")
def type_fields(
    request: Request,
    customer_type: str = "domestic",
    show_vat_breakdown: str = "",
    original_type: str = "",
    title: str = "",
    first_name: str = "",
    last_name: str = "",
    company_name: str = "",
):
    """Re-render the VAT-breakdown group (and, out of band, the name fields) when the type
    changes, so trade customers see the box locked on and the company name first."""
    new_type = "trade" if customer_type == "trade" else "domestic"
    requested = True if show_vat_breakdown == "on" else None
    values = {
        "customer_type": new_type,
        "show_vat_breakdown": resolve_vat_breakdown(original_type or None, new_type, requested),
        "title": title,
        "first_name": first_name,
        "last_name": last_name,
        "company_name": company_name,
    }
    return render(
        request,
        "customers/form.html",
        "customers/_type_change.html",
        {"values": values, "errors": {}, "customer": None, "duplicates": []},
    )


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
    return _after_write(
        request,
        f"/customers/{customer.id}",
        "customers/detail.html",
        _detail_context(customer),
        toasts,
    )


@router.get("/{customer_id}")
def customer_detail(request: Request, customer_id: int, session: Session = Depends(get_session)):
    customer = _get_or_404(session, customer_id)
    return render(request, "customers/detail.html", context=_detail_context(customer))


# --- Edit ----------------------------------------------------------------------------------


@router.get("/{customer_id}/edit")
def edit_customer(request: Request, customer_id: int, session: Session = Depends(get_session)):
    customer = _get_or_404(session, customer_id)
    return _form_page(request, _values_from_customer(customer), customer=customer)


@router.post("/{customer_id}")
async def update_customer(
    request: Request, customer_id: int, session: Session = Depends(get_session)
):
    customer = _get_or_404(session, customer_id)
    data = await request.form()
    values = _values_from_submission(data)
    form, errors = from_form(data)
    if form is None:
        return _form_page(request, values, customer=customer, errors=errors, status=422)

    if data.get("confirm_duplicate") != "1" and customer_service.phones_or_email_changed(
        customer, form
    ):
        duplicates = customer_service.find_duplicates(
            session, form.phones, form.email, exclude_id=customer.id
        )
        if duplicates:
            return _form_page(request, values, customer=customer, duplicates=duplicates)

    warnings = customer_service.update(session, customer, form)
    session.commit()
    toasts = [("success", "Customer updated")] + [("warning", w) for w in warnings]
    return _after_write(
        request,
        f"/customers/{customer.id}",
        "customers/detail.html",
        _detail_context(customer),
        toasts,
    )


# --- Archive and restore -------------------------------------------------------------------


@router.get("/{customer_id}/archive")
def archive_dialog(request: Request, customer_id: int, session: Session = Depends(get_session)):
    customer = _get_or_404(session, customer_id)
    context = _detail_context(customer, dialog="customers/_confirm_archive.html")
    return render(request, "customers/detail.html", "customers/_confirm_archive.html", context)


@router.post("/{customer_id}/archive")
def archive_customer(request: Request, customer_id: int, session: Session = Depends(get_session)):
    customer = _get_or_404(session, customer_id)
    customer_service.archive(session, customer)
    session.commit()
    return _after_write(
        request,
        f"/customers/{customer.id}",
        "customers/detail.html",
        _detail_context(customer),
        [("success", "Customer archived")],
    )


@router.post("/{customer_id}/restore")
def restore_customer(request: Request, customer_id: int, session: Session = Depends(get_session)):
    customer = _get_or_404(session, customer_id)
    customer_service.restore(session, customer)
    session.commit()
    return _after_write(
        request,
        f"/customers/{customer.id}",
        "customers/detail.html",
        _detail_context(customer),
        [("success", "Customer restored")],
    )


# --- Export --------------------------------------------------------------------------------


@router.get("/{customer_id}/export")
def export_customer(customer_id: int, session: Session = Depends(get_session)):
    customer = _get_or_404(session, customer_id)
    filename, data = _export_file(customer)
    return Response(
        content=data,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _export_file(customer: Customer) -> tuple[str, bytes]:
    body = json.dumps(customer_service.export_dict(customer), indent=2, ensure_ascii=False)
    filename = f"FloorPro-customer-{customer.reference}-{date.today().isoformat()}.json"
    return filename, body.encode("utf-8")


@router.post("/{customer_id}/export/save")
def save_customer_export(
    request: Request, customer_id: int, session: Session = Depends(get_session)
):
    """Desktop only: save the export through the native Save dialog, staying on the page."""
    dialogs = request.app.state.dialogs
    if dialogs is None:
        raise HTTPException(status_code=404)
    customer = _get_or_404(session, customer_id)
    filename, data = _export_file(customer)
    try:
        path = dialogs.save_path(filename)
        if path is not None:
            path.write_bytes(data)
    except OSError:
        log.exception("Export for %s could not be saved", customer.reference)
        toast = ("error", "The file couldn't be saved. Try a different folder.")
    else:
        toast = ("success", f"Exported to {path.name}") if path else ("info", "Export cancelled")
    return render(
        request,
        "customers/detail.html",
        "settings/_nothing.html",
        _detail_context(customer),
        toast=toast,
    )


# --- Erase ---------------------------------------------------------------------------------


@router.get("/{customer_id}/erase")
def erase_dialog(request: Request, customer_id: int, session: Session = Depends(get_session)):
    customer = _get_or_404(session, customer_id)
    context = _detail_context(customer, dialog="customers/_confirm_erase.html")
    return render(request, "customers/detail.html", "customers/_confirm_erase.html", context)


@router.post("/{customer_id}/erase")
async def erase_customer(
    request: Request, customer_id: int, session: Session = Depends(get_session)
):
    customer = _get_or_404(session, customer_id)
    data = await request.form()
    if not customer_service.erase(session, customer, data.get("confirm_name", "")):
        context = _detail_context(
            customer,
            dialog="customers/_confirm_erase.html",
            erase_error="The name doesn't match.",
            confirm_name=data.get("confirm_name", ""),
        )
        if is_htmx(request):
            # The boosted dialog form would otherwise swap the whole page; send the dialog back.
            return render(
                request,
                "customers/_confirm_erase.html",
                context=context,
                status_code=422,
                headers=DIALOG_ERROR_HEADERS,
            )
        return render(request, "customers/detail.html", context=context, status_code=422)

    session.commit()
    return _after_write(
        request,
        "/customers",
        "customers/index.html",
        _list_context(session),
        [("success", "Customer erased")],
    )
