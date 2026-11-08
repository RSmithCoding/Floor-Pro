"""Currency and VAT settings routes (contracts/routes.md, Settings)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from floorpro.db import get_session
from floorpro.domain.currency import SUPPORTED_CURRENCIES
from floorpro.domain.settings_history import canonical, snapshot_of
from floorpro.schemas.settings_form import SettingsForm, from_form
from floorpro.services import settings_service
from floorpro.templating import flash_redirect, is_htmx, render

router = APIRouter(prefix="/settings")

STALE_MESSAGE = "Settings were changed since you started. Please review them and save again."
ERROR_HEADERS = {"HX-Retarget": "#settings-form", "HX-Reswap": "outerHTML"}


def rate_input(value: Decimal | None) -> str:
    """``Decimal("20.00")`` -> ``"20"``, ``Decimal("17.50")`` -> ``"17.5"``."""
    if value is None:
        return ""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _values_from_settings(settings) -> dict:
    return {
        "currency_code": settings.currency_code,
        "vat_registered": settings.vat_registered,
        "vat_rate": rate_input(settings.vat_rate),
        "vat_number": settings.vat_number or "",
        "price_entry_mode": settings.price_entry_mode,
    }


def _values_from_submission(data) -> dict:
    return {
        "currency_code": data.get("currency_code", ""),
        "vat_registered": data.get("vat_registered") == "on",
        "vat_rate": data.get("vat_rate", ""),
        "vat_number": data.get("vat_number", ""),
        "price_entry_mode": data.get("price_entry_mode", ""),
    }


def _context(session: Session, values: dict, errors: dict | None = None, **extra) -> dict:
    return {
        "nav": "settings",
        "values": values,
        "errors": errors or {},
        "currencies": SUPPORTED_CURRENCIES.values(),
        "history": settings_service.history(session, per_page=10),
        "labels": settings_service.FIELD_LABELS,
        "display_value": settings_service.display_value,
        **extra,
    }


def _staged_fields(form: SettingsForm) -> dict[str, str]:
    """Hidden fields carried by the confirmation dialog (canonical values)."""
    return {
        "currency_code": form.currency_code,
        "vat_registered": "on" if form.vat_registered else "off",
        "vat_rate": canonical("vat_rate", form.vat_rate),
        "vat_number": form.vat_number or "",
        "price_entry_mode": form.price_entry_mode,
    }


@router.get("")
def settings_page(request: Request, session: Session = Depends(get_session)):
    settings, _ = settings_service.ensure_settings(session)
    return render(
        request, "settings/index.html", context=_context(session, _values_from_settings(settings))
    )


@router.post("")
async def stage_settings(request: Request, session: Session = Depends(get_session)):
    settings, _ = settings_service.ensure_settings(session)
    data = await request.form()
    form, errors = from_form(data, snapshot_of(settings))
    if form is None:
        return render(
            request,
            "settings/index.html",
            "settings/_form.html",
            _context(session, _values_from_submission(data), errors),
            status_code=422,
            headers=ERROR_HEADERS,
        )

    changes = settings_service.diff(snapshot_of(settings), form)
    values = _values_from_settings(settings)
    if not changes:
        return render(
            request,
            "settings/index.html",
            "settings/_nothing.html",
            _context(session, values),
            toast=("info", "Nothing to change"),
        )
    confirm = {
        "changes": changes,
        "fields": _staged_fields(form),
        "token": settings_service.make_token(form, settings),
    }
    return render(
        request,
        "settings/index.html",
        "settings/_confirm.html",
        _context(session, _values_from_submission(data), confirm=confirm),
    )


@router.post("/confirm")
async def confirm_settings(request: Request, session: Session = Depends(get_session)):
    settings, _ = settings_service.ensure_settings(session)
    data = await request.form()
    form, _errors = from_form(data, snapshot_of(settings))
    if form is None or not settings_service.verify_token(
        data.get("change_set_token", ""), form, settings
    ):
        return render(
            request,
            "settings/index.html",
            context=_context(session, _values_from_settings(settings)),
            status_code=409,
            toast=("error", STALE_MESSAGE),
        )

    settings_service.apply(session, form)
    session.commit()
    request.state.settings = settings
    if is_htmx(request):
        return render(
            request,
            "settings/index.html",
            context=_context(session, _values_from_settings(settings)),
            toast=("success", "Settings saved"),
            push_url="/settings",
        )
    return flash_redirect("/settings", "success", "Settings saved")


@router.get("/history")
def settings_history_page(request: Request, page: int = 1, session: Session = Depends(get_session)):
    context = {
        "nav": "settings",
        "history": settings_service.history(session, page=page),
        "labels": settings_service.FIELD_LABELS,
        "display_value": settings_service.display_value,
    }
    return render(request, "settings/history.html", "settings/_history.html", context)


@router.get("/form/vat-fields")
def vat_fields(
    request: Request, vat_registered: str = "", vat_rate: str = "", vat_number: str = ""
):
    values = {
        "vat_registered": vat_registered == "on",
        "vat_rate": vat_rate,
        "vat_number": vat_number,
    }
    return render(
        request,
        "settings/index.html",
        "settings/_vat_fields.html",
        {"values": values, "errors": {}},
    )
