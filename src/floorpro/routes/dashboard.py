"""Dashboard (home screen) and the health check used by the desktop launcher."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from floorpro.domain.backups import backup_status
from floorpro.services import backup_service
from floorpro.templating import local_datetime_filter, render

router = APIRouter()


def last_backup_text(when: datetime | None, now: datetime) -> str | None:
    """ "today at 09:02", "yesterday at 17:30", or "3 Nov 2026, 17:30"."""
    if when is None:
        return None
    local, today = when.astimezone(), now.astimezone().date()
    if local.date() == today:
        return f"today at {local:%H:%M}"
    if local.date() == today - timedelta(days=1):
        return f"yesterday at {local:%H:%M}"
    return local_datetime_filter(when)


@router.get("/")
def dashboard(request: Request):
    backup_service.maybe_run_daily(request.app)
    prefs = backup_service.load_prefs()
    now = backup_service.now()
    context = {
        "nav": "dashboard",
        "backup_warnings": backup_status(prefs, backup_service.key_is_set(), now),
        "last_backup": last_backup_text(prefs.last_success_at, now),
    }
    return render(request, "dashboard.html", context=context)


@router.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"
