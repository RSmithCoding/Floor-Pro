"""Settings form parsing and validation (FR-001 to FR-010)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from floorpro.domain.currency import SUPPORTED_CURRENCIES
from floorpro.domain.settings_history import SettingsSnapshot
from floorpro.domain.validation import normalise_vat_number, validate_vat_rate

CURRENCY_ERROR = "Choose a currency from the list."
MODE_ERROR = "Choose how prices are entered."


class SettingsForm(BaseModel):
    model_config = ConfigDict(frozen=True)

    currency_code: str
    vat_registered: bool
    vat_rate: Decimal
    vat_number: str | None
    price_entry_mode: Literal["inc_vat", "ex_vat"]

    @field_validator("currency_code")
    @classmethod
    def _check_currency(cls, value: str) -> str:
        if value not in SUPPORTED_CURRENCIES:
            raise ValueError(CURRENCY_ERROR)
        return value

    def snapshot(self) -> SettingsSnapshot:
        return SettingsSnapshot(**self.model_dump())


def from_form(
    data: Mapping[str, str], current: SettingsSnapshot
) -> tuple[SettingsForm | None, dict[str, str]]:
    """Parse submitted settings. When not VAT registered, the rate and number are optional:
    blank or invalid values fall back to the current ones, so they're restored on re-registering.
    """
    errors: dict[str, str] = {}
    registered = data.get("vat_registered") == "on"
    raw_rate = (data.get("vat_rate") or "").strip()
    raw_number = (data.get("vat_number") or "").strip()

    try:
        rate = validate_vat_rate(raw_rate)
    except ValueError as exc:
        rate = current.vat_rate
        if registered:
            errors["vat_rate"] = str(exc)

    number: str | None = None
    if raw_number:
        try:
            number = normalise_vat_number(raw_number)
        except ValueError as exc:
            number = current.vat_number
            if registered:
                errors["vat_number"] = str(exc)
    elif not registered:
        number = current.vat_number

    mode = data.get("price_entry_mode") or ""
    if mode not in ("inc_vat", "ex_vat"):
        errors["price_entry_mode"] = MODE_ERROR

    try:
        form = SettingsForm(
            currency_code=data.get("currency_code") or "",
            vat_registered=registered,
            vat_rate=rate,
            vat_number=number,
            price_entry_mode=mode if mode in ("inc_vat", "ex_vat") else current.price_entry_mode,
        )
    except ValidationError as exc:
        for error in exc.errors():
            field = str(error["loc"][0])
            errors.setdefault(field, error["msg"].removeprefix("Value error, "))
        return None, errors
    return (None, errors) if errors else (form, {})
