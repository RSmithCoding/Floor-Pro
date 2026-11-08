"""Recovery screen, shown when the shop's database can't be opened at startup (FR-025).

Every route is 404 unless the app is in recovery mode. Nothing here uses a database session.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from floorpro import paths
from floorpro.backup_file import BackupError, NotABackup
from floorpro.domain.backups import most_recent
from floorpro.schemas.backup_forms import (
    PASSWORD_NEEDED_ERROR,
    parse_restore_confirm,
    parse_start_again,
)
from floorpro.services import backup_service, recovery_service
from floorpro.templating import (
    flash_redirect,
    htmx_redirect,
    is_htmx,
    local_datetime_filter,
    render,
)

router = APIRouter(prefix="/recovery")
log = logging.getLogger(__name__)


def require_recovery(request: Request) -> None:
    if request.app.state.recovery is None:
        raise HTTPException(status_code=404)


def recovery_context(request: Request, **extra) -> dict:
    backups = [b for b in backup_service.list_backups() if not b.damaged]
    context = {
        "info": request.app.state.recovery,
        "backups": backups,
        "latest": most_recent(backups),
        "current_key_id": backup_service.current_key_id(),
        "desktop": request.app.state.dialogs is not None,
    }
    context.update(extra)
    return context


def recovery_page(request: Request, *, status_code: int = 200, **extra):
    return render(
        request,
        "recovery/index.html",
        context=recovery_context(request, **extra),
        status_code=status_code,
    )


def finish_restore(request: Request, path, password: str | None):
    """Restore in recovery mode and leave it; errors re-render the recovery screen."""
    info = backup_service.read_info(path, "file")
    if info.damaged:
        return recovery_page(request, status_code=422, error=NotABackup.message)
    if info.needs_password(backup_service.current_key_id()) and not password:
        return recovery_page(request, status_code=422, error=PASSWORD_NEEDED_ERROR)
    try:
        recovery_service.restore_in_recovery(path, password)
    except BackupError as exc:
        return recovery_page(request, status_code=422, error=exc.message)
    request.app.state.reopen_database()
    when = local_datetime_filter(info.created_at)
    return flash_redirect("/", "success", f"Restored the backup from {when}")


@router.get("")
def recovery_index(request: Request):
    require_recovery(request)
    return recovery_page(request)


@router.post("/restore")
async def recovery_restore(request: Request):
    require_recovery(request)
    form = await request.form()
    try:
        path = backup_service.resolve(str(form.get("loc", "")), str(form.get("name", "")))
    except LookupError:
        return recovery_page(request, status_code=422, error="That backup is no longer available.")
    return finish_restore(request, path, str(form.get("password") or "") or None)


@router.post("/start-fresh")
async def recovery_start_fresh(request: Request):
    require_recovery(request)
    errors = parse_start_again(await request.form())
    if errors:
        return recovery_page(request, status_code=422, start_errors=errors)
    recovery_service.start_fresh()
    request.app.state.reopen_database()
    return flash_redirect(
        "/",
        "success",
        f"Started with no data. The damaged data was kept in {paths.damaged_dir()}.",
    )


# --- Restore from a file in recovery mode (US4) ----------------------------------------------

CONFIRM_ACTION = "/recovery/restore-file/confirm"


def file_dialog(request: Request, path, *, status_code: int = 200, **extra):
    """The shared restore dialog: swapped into #modal for HTMX, else on the recovery page."""
    from floorpro.routes.backups import DIALOG_ERROR_HEADERS, restore_target

    info, refusal = restore_target(path)
    if refusal and status_code == 200:
        status_code = 422
    context = recovery_context(
        request,
        backup=info,
        refusal=refusal,
        action=CONFIRM_ACTION,
        source_token=backup_service.make_source_token(path),
        needs_password=info.needs_password(backup_service.current_key_id()),
        **extra,
    )
    if is_htmx(request):
        headers = DIALOG_ERROR_HEADERS if status_code >= 400 else None
        return render(
            request,
            "backups/_confirm_restore.html",
            context=context,
            status_code=status_code,
            headers=headers,
        )
    context["dialog"] = "backups/_confirm_restore.html"
    return render(request, "recovery/index.html", context=context, status_code=status_code)


@router.post("/restore-file/choose")
def recovery_file_choose(request: Request):
    require_recovery(request)
    dialogs = request.app.state.dialogs
    if dialogs is None:
        raise HTTPException(status_code=404)
    path = dialogs.open_file()
    if path is None:
        return Response(status_code=204)
    return file_dialog(request, path)


@router.post("/restore-file/upload")
async def recovery_file_upload(request: Request):
    require_recovery(request)
    upload = (await request.form()).get("file")
    if upload is None or not hasattr(upload, "file"):
        return recovery_page(request, status_code=422, error=NotABackup.message)
    return file_dialog(request, backup_service.save_upload(upload.file))


@router.post("/restore-file/confirm")
async def recovery_file_confirm(request: Request):
    from floorpro import backup_file
    from floorpro.routes.backups import FILE_GONE

    require_recovery(request)
    form = await request.form()
    try:
        path = backup_service.read_source_token(str(form.get("source_token") or ""))
    except LookupError:
        return recovery_page(request, status_code=409, error=FILE_GONE)
    info = backup_service.read_info(path, "file")
    password, errors = parse_restore_confirm(
        form, info.needs_password(backup_service.current_key_id())
    )
    if errors:
        return file_dialog(request, path, status_code=422, errors=errors)
    try:
        recovery_service.restore_in_recovery(path, password)
    except backup_file.WrongPassword as exc:
        return file_dialog(request, path, status_code=422, errors={"password": exc.message})
    except BackupError as exc:
        return file_dialog(request, path, status_code=422, restore_error=exc.message)
    backup_service.discard_upload(path)
    request.app.state.reopen_database()
    when = local_datetime_filter(info.created_at)
    return htmx_redirect(request, "/", "success", f"Restored the backup from {when}")
