"""Jinja templates, filters, and the full-page/partial/toast rendering helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from floorpro.domain.currency import format_money
from floorpro.paths import resource_path, secret_key

templates = Jinja2Templates(directory=str(resource_path("templates")))

FLASH_COOKIE = "flash"
Toast = tuple[str, str]  # (kind, message); kind is "success" | "error" | "info" | "warning"


# --- Filters -------------------------------------------------------------------------------


@pass_context
def money_filter(context, value: Decimal | None) -> str:
    if value is None:
        return ""
    settings = context.get("settings")
    code = settings.currency_code if settings is not None else "GBP"
    return format_money(value, code)


def percent_filter(value: Decimal | None) -> str:
    """``Decimal("17.50")`` -> ``"17.5%"``, ``Decimal("20.00")`` -> ``"20%"``."""
    if value is None:
        return ""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


def local_datetime_filter(value: datetime | None) -> str:
    """UTC -> local time, e.g. ``"7 Nov 2026, 14:05"``."""
    if value is None:
        return ""
    local = value.astimezone()
    return f"{local.day} {local:%b %Y, %H:%M}"


def local_date_filter(value: datetime | None) -> str:
    """UTC -> local date, e.g. ``"7 Nov 2026"``."""
    if value is None:
        return ""
    local = value.astimezone()
    return f"{local.day} {local:%b %Y}"


templates.env.filters["money"] = money_filter
templates.env.filters["percent"] = percent_filter
templates.env.filters["local_datetime"] = local_datetime_filter
templates.env.filters["local_date"] = local_date_filter


# --- Request helpers -----------------------------------------------------------------------


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def is_partial(request: Request) -> bool:
    """True for HTMX requests that swap a fragment (not boosted navigation or history restore)."""
    return (
        is_htmx(request)
        and request.headers.get("HX-Boosted") != "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


# --- Flash messages (research.md §15) ------------------------------------------------------


def _sign(payload: bytes) -> str:
    return hmac.new(secret_key(), payload, hashlib.sha256).hexdigest()


def _encode_flash(toast: Toast) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(list(toast)).encode())
    return f"{payload.decode()}.{_sign(payload)}"


def _decode_flash(value: str) -> Toast | None:
    try:
        payload, signature = value.rsplit(".", 1)
        if not hmac.compare_digest(_sign(payload.encode()), signature):
            return None
        kind, message = json.loads(base64.urlsafe_b64decode(payload))
        return str(kind), str(message)
    except (ValueError, TypeError):
        return None


def flash_redirect(url: str, kind: str, message: str) -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        FLASH_COOKIE, _encode_flash((kind, message)), max_age=60, httponly=True, samesite="lax"
    )
    return response


def pop_flash(request: Request) -> Toast | None:
    value = request.cookies.get(FLASH_COOKIE)
    return _decode_flash(value) if value else None


# --- Rendering -----------------------------------------------------------------------------


def _toast_fragment(toasts: list[Toast]) -> str:
    template = templates.env.get_template("components/toast_oob.html")
    return template.render(toasts=toasts)


def render(
    request: Request,
    page: str,
    partial: str | None = None,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    toast: Toast | list[Toast] | None = None,
    push_url: str | None = None,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    """Render ``partial`` for fragment HTMX requests, otherwise the full ``page``.

    Toasts are rendered inside ``#toasts`` on full pages, or sent out-of-band with partials.
    """
    toasts: list[Toast] = []
    if isinstance(toast, tuple):
        toasts.append(toast)
    elif toast:
        toasts.extend(toast)

    flashed = pop_flash(request)
    if flashed:
        toasts.insert(0, flashed)
    app_state = request.app.state
    if getattr(app_state, "settings_notice", False):
        app_state.settings_notice = False
        toasts.insert(
            0,
            ("info", "Settings were missing and have been reset to the defaults (GBP, 20% VAT)."),
        )

    ctx = {"request": request, "settings": getattr(request.state, "settings", None)}
    ctx.update(context or {})

    use_partial = partial is not None and is_partial(request)
    if use_partial:
        body = templates.env.get_template(partial).render(ctx)
        if toasts:
            body += _toast_fragment(toasts)
    else:
        ctx["toasts"] = toasts
        body = templates.env.get_template(page).render(ctx)

    response = HTMLResponse(body, status_code=status_code, headers=headers)
    if push_url:
        response.headers["HX-Push-Url"] = push_url
    if flashed:
        response.delete_cookie(FLASH_COOKIE)
    return response
