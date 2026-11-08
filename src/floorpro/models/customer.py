"""Customer records (data-model.md §3)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from floorpro.domain.customers import display_name, format_reference, sort_name
from floorpro.models.base import Base, UTCDateTime, utcnow


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (
        CheckConstraint("customer_type IN ('domestic','trade')", name="customer_type"),
        CheckConstraint(
            "customer_type = 'domestic' OR show_vat_breakdown = 1", name="trade_vat_breakdown"
        ),
        CheckConstraint(
            "COALESCE(TRIM(first_name),'') <> '' OR COALESCE(TRIM(last_name),'') <> '' "
            "OR COALESCE(TRIM(company_name),'') <> ''",
            name="has_name",
        ),
        CheckConstraint(
            "mobile_phone IS NOT NULL OR other_phone IS NOT NULL OR email IS NOT NULL",
            name="has_contact",
        ),
        Index("ix_customer_archived_type", "is_archived", "customer_type"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_type: Mapped[str] = mapped_column(Text, default="domestic")
    show_vat_breakdown: Mapped[bool] = mapped_column(Boolean, default=False)

    title: Mapped[str | None] = mapped_column(String(20))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100, collation="NOCASE"), index=True)
    company_name: Mapped[str | None] = mapped_column(String(200, collation="NOCASE"), index=True)

    mobile_phone: Mapped[str | None] = mapped_column(String(30))
    mobile_phone_digits: Mapped[str | None] = mapped_column(Text, index=True)
    other_phone: Mapped[str | None] = mapped_column(String(30))
    other_phone_digits: Mapped[str | None] = mapped_column(Text, index=True)
    email: Mapped[str | None] = mapped_column(Text(collation="NOCASE"), index=True)

    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    town: Mapped[str | None] = mapped_column(String(100))
    county: Mapped[str | None] = mapped_column(String(100))
    postcode: Mapped[str | None] = mapped_column(Text)
    postcode_compact: Mapped[str | None] = mapped_column(Text, index=True)

    notes: Mapped[str | None] = mapped_column(Text)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    @property
    def reference(self) -> str:
        return format_reference(self.id)

    @property
    def display_name(self) -> str:
        return display_name(self.first_name, self.last_name, self.company_name)

    @property
    def sort_name(self) -> str:
        return sort_name(self.first_name, self.last_name, self.company_name)

    @property
    def primary_phone(self) -> str | None:
        return self.mobile_phone or self.other_phone
