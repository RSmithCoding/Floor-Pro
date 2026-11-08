"""Backup form parsing: passwords, restore confirmation and Start with no data (data-model §6)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from floorpro.domain.backups import validate_new_password

CONFIRM_RESTORE_ERROR = "Type RESTORE to confirm."
PASSWORD_NEEDED_ERROR = "Enter the password this backup was made with."
CURRENT_MISSING_ERROR = "Enter your current backup password."
CURRENT_WRONG_ERROR = "That isn't the current backup password."
START_AGAIN_ERROR = "Type START AGAIN to confirm."


def _text(form: Mapping[str, Any], name: str) -> str:
    value = form.get(name)
    return value if isinstance(value, str) else ""


def parse_new_password(form: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    password = _text(form, "password")
    return password, validate_new_password(password, _text(form, "password_confirm"))


def parse_change_password(
    form: Mapping[str, Any], check_current: Callable[[str], bool]
) -> tuple[tuple[str, str], dict[str, str]]:
    current = _text(form, "current_password")
    new, errors = parse_new_password(form)
    if not current:
        errors = {"current_password": CURRENT_MISSING_ERROR, **errors}
    elif not check_current(current):
        errors = {"current_password": CURRENT_WRONG_ERROR, **errors}
    return (current, new), errors


def parse_restore_confirm(
    form: Mapping[str, Any], needs_password: bool
) -> tuple[str | None, dict[str, str]]:
    """Returns (password or None, errors). RESTORE is accepted in any case, spaces trimmed."""
    errors: dict[str, str] = {}
    if _text(form, "confirm").strip().upper() != "RESTORE":
        errors["confirm"] = CONFIRM_RESTORE_ERROR
    password = _text(form, "password") or None
    if needs_password and not password:
        errors["password"] = PASSWORD_NEEDED_ERROR
    return (password if needs_password else None), errors


def parse_start_again(form: Mapping[str, Any]) -> dict[str, str]:
    if _text(form, "confirm").strip() != "START AGAIN":
        return {"confirm": START_AGAIN_ERROR}
    return {}
