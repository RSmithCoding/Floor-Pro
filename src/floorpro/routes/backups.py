"""Backups screen: password, Back up now, the list, restore, folder and copies.

Routes only parse forms, call ``backup_service`` and render (Principle VI). Restore routes
never take a database session: the restore swap must not wait on a lock held by its own
request (research.md §8).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from floorpro import backup_file
from floorpro.backup_file import BackupError, NotABackup
from floorpro.domain.backups import BackupInfo, BackupKind, most_recent
from floorpro.schemas.backup_forms import (
    parse_change_password,
    parse_new_password,
    parse_restore_confirm,
)
from floorpro.services import backup_service
from floorpro.templating import (
    Toast,
    flash_redirect,
    htmx_redirect,
    is_htmx,
    local_datetime_filter,
    render,
)

router = APIRouter(prefix="/backups")
log = logging.getLogger(__name__)

DIALOG_ERROR_HEADERS = {"HX-Retarget": "#modal", "HX-Reswap": "innerHTML"}


def backups_context(request: Request, **extra) -> dict:
    key = backup_service.load_key()
    prefs = backup_service.load_prefs()
    context: dict = {"nav": "backups", "key_set": key is not None, "prefs": prefs}
    if key is not None:
        backups = backup_service.list_backups()
        latest = most_recent(backups)
        locations = {loc.name: loc for loc in backup_service.locations()}
        context.update(
            backups=backups,
            latest=latest,
            current_key_id=key.key_id,
            folder=locations.get("folder"),
            desktop=request.app.state.dialogs is not None,
        )
    context.update(extra)
    return context


def backups_page(
    request: Request,
    *,
    toast: Toast | list[Toast] | None = None,
    status_code: int = 200,
    push: bool = False,
    **extra,
):
    return render(
        request,
        "backups/index.html",
        context=backups_context(request, **extra),
        toast=toast,
        status_code=status_code,
        push_url="/backups" if push else None,
    )


@router.get("")
def backups_index(request: Request):
    return backups_page(request)


def _done(request: Request, message: str, kind: str = "success"):
    """Success after a write: re-render the Backups screen for HTMX, else redirect + flash."""
    if is_htmx(request):
        return backups_page(request, toast=(kind, message), push=True)
    return flash_redirect("/backups", kind, message)


def _dialog(request: Request, template: str, *, status_code: int = 200, **extra):
    """A dialog swapped into #modal (errors re-target #modal from boosted forms)."""
    if is_htmx(request):
        headers = DIALOG_ERROR_HEADERS if status_code >= 400 else None
        return render(
            request,
            template,
            context=backups_context(request, **extra),
            status_code=status_code,
            headers=headers,
        )
    return backups_page(request, status_code=status_code, dialog=template, **extra)


# --- Password (US5) --------------------------------------------------------------------------


@router.post("/password")
async def set_password(request: Request):
    if backup_service.key_is_set():
        return backups_page(
            request, toast=("error", "A backup password is already set."), status_code=409
        )
    password, errors = parse_new_password(await request.form())
    if errors:
        if is_htmx(request):
            return render(
                request,
                "backups/_set_password.html",
                context={"password_errors": errors},
                status_code=422,
                headers={"HX-Retarget": "#backup-password-form", "HX-Reswap": "outerHTML"},
            )
        return backups_page(request, status_code=422, password_errors=errors)
    backup_service.set_password(password)
    backup_service.maybe_run_daily(request.app)  # the first automatic backup (US3)
    return _done(request, "Backup password set")


@router.get("/password/change")
def change_password_dialog(request: Request):
    if not backup_service.key_is_set():
        raise HTTPException(status_code=404)
    return _dialog(request, "backups/_change_password.html")


@router.post("/password/change")
async def change_password(request: Request):
    if not backup_service.key_is_set():
        raise HTTPException(status_code=404)
    (current, new), errors = parse_change_password(
        await request.form(), backup_service.check_current_password
    )
    if errors:
        return _dialog(
            request, "backups/_change_password.html", status_code=422, change_errors=errors
        )
    backup_service.change_password(current, new)
    return _done(request, "Backup password changed")


# --- Back up now (US1) -----------------------------------------------------------------------


@router.post("")
def back_up_now(request: Request):
    try:
        info = backup_service.make_backup(BackupKind.MANUAL)
    except BackupError as exc:
        return backups_page(request, toast=("error", exc.message), push=is_htmx(request))
    noun = "customer" if info.customers == 1 else "customers"
    return _done(request, f"Backup made · {info.customers:,} {noun}")


# --- Restore (US2) ---------------------------------------------------------------------------

LEGACY_REFUSAL = (
    "This older copy isn't protected. It can only be restored from the recovery screen."
)


def _resolve_or_404(loc: str, name: str):
    try:
        return backup_service.resolve(loc, name)
    except LookupError as exc:
        raise HTTPException(status_code=404) from exc


def restore_target(path) -> tuple[BackupInfo | None, str | None]:
    """(backup info, refusal message) for the restore dialog."""
    info = backup_service.read_info(path, "file")
    if info.damaged:
        return info, NotABackup.message
    if not info.protected:
        return info, LEGACY_REFUSAL
    try:
        backup_service.open_backup(path)
    except BackupError as exc:
        return info, exc.message
    return info, None


def restore_dialog(
    request: Request, path, action: str, *, status_code: int = 200, source_token=None, **extra
):
    info, refusal = restore_target(path)
    return _dialog(
        request,
        "backups/_confirm_restore.html",
        status_code=status_code,
        backup=info,
        refusal=refusal,
        action=action,
        source_token=source_token,
        needs_password=info.needs_password(backup_service.current_key_id()),
        **extra,
    )


async def do_restore(request: Request, path, action: str, source_token: str | None = None):
    """Shared by restore-from-list and restore-from-file. Never opens a database session."""
    info, refusal = restore_target(path)
    if refusal:
        return restore_dialog(request, path, action, status_code=422, source_token=source_token)
    needs_password = info.needs_password(backup_service.current_key_id())
    password, errors = parse_restore_confirm(await request.form(), needs_password)
    if errors:
        return restore_dialog(
            request, path, action, status_code=422, source_token=source_token, errors=errors
        )
    try:
        backup_service.restore(path, request.app.state.engine, password)
    except backup_file.WrongPassword as exc:
        errors = {"password": exc.message}
        return restore_dialog(
            request, path, action, status_code=422, source_token=source_token, errors=errors
        )
    except BackupError as exc:
        return restore_dialog(
            request,
            path,
            action,
            status_code=422,
            source_token=source_token,
            restore_error=exc.message,
        )
    when = local_datetime_filter(info.created_at)
    return htmx_redirect(request, "/", "success", f"Restored the backup from {when}")


@router.get("/{loc}/{name}/restore")
def restore_confirm(request: Request, loc: str, name: str):
    path = _resolve_or_404(loc, name)
    return restore_dialog(request, path, f"/backups/{loc}/{name}/restore")


@router.post("/{loc}/{name}/restore")
async def restore_backup(request: Request, loc: str, name: str):
    path = _resolve_or_404(loc, name)
    return await do_restore(request, path, f"/backups/{loc}/{name}/restore")


# --- Automatic backups (US3) -----------------------------------------------------------------


@router.post("/automatic")
async def set_automatic(request: Request):
    enabled = (await request.form()).get("auto_enabled") == "on"
    backup_service.set_auto_enabled(enabled)
    if enabled:
        backup_service.maybe_run_daily(request.app)
    return _done(request, "Automatic backups on" if enabled else "Automatic backups off")


# --- Folder (US4) ----------------------------------------------------------------------------


def _dialogs_or_404(request: Request):
    dialogs = request.app.state.dialogs
    if dialogs is None:
        raise HTTPException(status_code=404)
    return dialogs


@router.post("/folder/choose")
def choose_folder(request: Request):
    chosen = _dialogs_or_404(request).choose_folder()
    if chosen is None:
        return Response(status_code=204)
    try:
        folder = backup_service.set_folder(chosen)
    except BackupError as exc:
        return backups_page(request, toast=("error", exc.message), push=is_htmx(request))
    return _done(request, f"Backups will be saved to {folder}")


@router.post("/folder")
async def set_folder(request: Request):
    value = str((await request.form()).get("folder") or "").strip()
    try:
        folder = backup_service.set_folder(value)
    except BackupError as exc:
        return backups_page(request, status_code=422, folder_error=exc.message, folder_value=value)
    return _done(request, f"Backups will be saved to {folder}")


@router.post("/folder/reset")
def reset_folder(request: Request):
    backup_service.reset_folder()
    return _done(request, "Backups will be saved on this computer")


# --- Save a copy, download, delete (US4) -----------------------------------------------------


@router.post("/{loc}/{name}/save-copy")
def save_copy(request: Request, loc: str, name: str):
    dialogs = _dialogs_or_404(request)
    _resolve_or_404(loc, name)
    target = dialogs.save_path(name)
    if target is None:
        return Response(status_code=204)
    try:
        saved = backup_service.save_copy(loc, name, target)
        toast = ("success", f"Saved a copy to {saved}")
    except OSError:
        log.exception("Saving a copy of %s failed", name)
        toast = ("error", "The copy couldn't be saved. Try a different folder.")
    return render(
        request,
        "backups/index.html",
        "settings/_nothing.html",
        backups_context(request),
        toast=toast,
    )


@router.get("/{loc}/{name}/download")
def download(loc: str, name: str):
    path = _resolve_or_404(loc, name)
    return FileResponse(path, media_type="application/octet-stream", filename=name)


def _is_latest(loc: str, name: str) -> bool:
    latest = most_recent(backup_service.list_backups())
    return latest is not None and (latest.location, latest.filename) == (loc, name)


@router.get("/{loc}/{name}/delete")
def delete_dialog(request: Request, loc: str, name: str):
    path = _resolve_or_404(loc, name)
    latest = _is_latest(loc, name)
    return _dialog(
        request,
        "backups/_confirm_delete.html",
        status_code=409 if latest else 200,
        backup=backup_service.read_info(path, loc),
        cannot_delete=latest,
        action=f"/backups/{loc}/{name}/delete",
    )


@router.post("/{loc}/{name}/delete")
def delete_backup(request: Request, loc: str, name: str):
    _resolve_or_404(loc, name)
    try:
        backup_service.delete_backup(loc, name)
    except BackupError as exc:
        return backups_page(request, toast=("error", exc.message), status_code=409)
    return _done(request, "Backup deleted")


# --- Restore from a file (US4) ---------------------------------------------------------------

FILE_GONE = "That file is no longer available. Choose it again."


@router.post("/restore-file/choose")
def restore_file_choose(request: Request):
    path = _dialogs_or_404(request).open_file()
    if path is None:
        return Response(status_code=204)
    token = backup_service.make_source_token(path)
    return restore_dialog(request, path, "/backups/restore-file/confirm", source_token=token)


@router.post("/restore-file/upload")
async def restore_file_upload(request: Request):
    upload = (await request.form()).get("file")
    if upload is None or not hasattr(upload, "file"):
        return backups_page(request, status_code=422, toast=("error", NotABackup.message))
    path = backup_service.save_upload(upload.file)
    _, refusal = restore_target(path)
    token = backup_service.make_source_token(path)
    return restore_dialog(
        request,
        path,
        "/backups/restore-file/confirm",
        status_code=422 if refusal else 200,
        source_token=token,
    )


@router.post("/restore-file/confirm")
async def restore_file_confirm(request: Request):
    token = str((await request.form()).get("source_token") or "")
    try:
        path = backup_service.read_source_token(token)
    except LookupError:
        return backups_page(request, status_code=409, toast=("error", FILE_GONE))
    response = await do_restore(request, path, "/backups/restore-file/confirm", token)
    if response.status_code < 400:
        backup_service.discard_upload(path)
    return response
