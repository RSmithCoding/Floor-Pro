"""Business-wide currency and VAT settings, and their change history (data-model.md §1–2)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from floorpro.models.base import Base, Percent, UTCDateTime, utcnow


class PriceEntryMode(StrEnum):
    INC_VAT = "inc_vat"
    EX_VAT = "ex_vat"


SETTINGS_FIELDS = ("currency_code", "vat_registered", "vat_rate", "vat_number", "price_entry_mode")


class BusinessSettings(Base):
    __tablename__ = "business_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("vat_rate_bp BETWEEN 0 AND 10000", name="vat_rate_range"),
        CheckConstraint("price_entry_mode IN ('inc_vat','ex_vat')", name="price_entry_mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    currency_code: Mapped[str] = mapped_column(String(3), default="GBP")
    vat_registered: Mapped[bool] = mapped_column(Boolean, default=True)
    vat_rate: Mapped[Decimal] = mapped_column("vat_rate_bp", Percent, default=Decimal("20.00"))
    vat_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_entry_mode: Mapped[str] = mapped_column(Text, default=PriceEntryMode.INC_VAT.value)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SettingsChange(Base):
    __tablename__ = "settings_change"
    __table_args__ = (
        CheckConstraint(
            "field IN ('currency_code','vat_registered','vat_rate','vat_number',"
            "'price_entry_mode')",
            name="field",
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_set_id: Mapped[str] = mapped_column(String(36))
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    field: Mapped[str] = mapped_column(Text)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
