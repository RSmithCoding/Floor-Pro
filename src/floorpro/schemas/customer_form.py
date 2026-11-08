"""Customer form parsing and validation, with plain-English messages per field."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from floorpro.domain.validation import validate_email, validate_phone

NAME_ERROR = "Enter a first name, last name or company name."
CONTACT_ERROR = "Add a phone number or email address."

TEXT_FIELDS = (
    "title",
    "first_name",
    "last_name",
    "company_name",
    "mobile_phone",
    "other_phone",
    "email",
    "address_line1",
    "address_line2",
    "town",
    "county",
    "postcode",
    "notes",
)

Opt = str | None


class CustomerForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[Opt, Field(max_length=20)] = None
    first_name: Annotated[Opt, Field(max_length=100)] = None
    last_name: Annotated[Opt, Field(max_length=100)] = None
    company_name: Annotated[Opt, Field(max_length=200)] = None
    mobile_phone: Annotated[Opt, Field(max_length=30)] = None
    other_phone: Annotated[Opt, Field(max_length=30)] = None
    email: Opt = None
    address_line1: Annotated[Opt, Field(max_length=200)] = None
    address_line2: Annotated[Opt, Field(max_length=200)] = None
    town: Annotated[Opt, Field(max_length=100)] = None
    county: Annotated[Opt, Field(max_length=100)] = None
    postcode: Opt = None
    notes: Opt = None  # no length limit
    marketing_consent: bool = False
    customer_type: Literal["domestic", "trade"] = "domestic"
    show_vat_breakdown: bool = False

    @field_validator(*TEXT_FIELDS, mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("mobile_phone", "other_phone")
    @classmethod
    def _check_phone(cls, value):
        if value is not None and (error := validate_phone(value)):
            raise ValueError(error)
        return value

    @field_validator("email")
    @classmethod
    def _check_email(cls, value):
        if value is not None and (error := validate_email(value)):
            raise ValueError(error)
        return value

    @property
    def phones(self) -> list[str]:
        return [p for p in (self.mobile_phone, self.other_phone) if p]


def _message(error: dict) -> str:
    if error["type"] == "string_too_long":
        return f"Enter at most {error['ctx']['max_length']} characters."
    if error["type"] == "literal_error":
        return "Choose one of the options."
    message = error["msg"]
    return message.removeprefix("Value error, ")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def from_form(data: Mapping[str, str]) -> tuple[CustomerForm | None, dict[str, str]]:
    """Parse submitted form data. Returns ``(form, {})`` or ``(None, {field: message})``."""
    raw = {name: data.get(name) for name in TEXT_FIELDS}
    raw["marketing_consent"] = data.get("marketing_consent") == "on"
    raw["show_vat_breakdown"] = data.get("show_vat_breakdown") == "on"
    raw["customer_type"] = data.get("customer_type") or "domestic"

    errors: dict[str, str] = {}
    if not any(_clean(raw[f]) for f in ("first_name", "last_name", "company_name")):
        errors["name"] = NAME_ERROR
    if not any(_clean(raw[f]) for f in ("mobile_phone", "other_phone", "email")):
        errors["contact"] = CONTACT_ERROR

    try:
        form = CustomerForm(**raw)
    except ValidationError as exc:
        for error in exc.errors():
            field = str(error["loc"][0]) if error["loc"] else "form"
            errors.setdefault(field, _message(error))
        return None, errors
    return (None, errors) if errors else (form, {})
