"""Initial schema: business settings, settings history, customers.

Revision ID: 0001
Revises:
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("vat_registered", sa.Boolean(), nullable=False),
        sa.Column("vat_rate_bp", sa.Integer(), nullable=False),
        sa.Column("vat_number", sa.Text(), nullable=True),
        sa.Column("price_entry_mode", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_business_settings_single_row")),
        sa.CheckConstraint(
            "vat_rate_bp BETWEEN 0 AND 10000", name=op.f("ck_business_settings_vat_rate_range")
        ),
        sa.CheckConstraint(
            "price_entry_mode IN ('inc_vat','ex_vat')",
            name=op.f("ck_business_settings_price_entry_mode"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_settings")),
    )

    op.create_table(
        "settings_change",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("change_set_id", sa.String(length=36), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "field IN ('currency_code','vat_registered','vat_rate','vat_number',"
            "'price_entry_mode')",
            name=op.f("ck_settings_change_field"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings_change")),
        sqlite_autoincrement=True,
    )
    op.create_index(
        op.f("ix_settings_change_changed_at"), "settings_change", ["changed_at"], unique=False
    )

    op.create_table(
        "customer",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_type", sa.Text(), nullable=False),
        sa.Column("show_vat_breakdown", sa.Boolean(), nullable=False),
        sa.Column("title", sa.String(length=20), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100, collation="NOCASE"), nullable=True),
        sa.Column("company_name", sa.String(length=200, collation="NOCASE"), nullable=True),
        sa.Column("mobile_phone", sa.String(length=30), nullable=True),
        sa.Column("mobile_phone_digits", sa.Text(), nullable=True),
        sa.Column("other_phone", sa.String(length=30), nullable=True),
        sa.Column("other_phone_digits", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(collation="NOCASE"), nullable=True),
        sa.Column("address_line1", sa.String(length=200), nullable=True),
        sa.Column("address_line2", sa.String(length=200), nullable=True),
        sa.Column("town", sa.String(length=100), nullable=True),
        sa.Column("county", sa.String(length=100), nullable=True),
        sa.Column("postcode", sa.Text(), nullable=True),
        sa.Column("postcode_compact", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "customer_type IN ('domestic','trade')", name=op.f("ck_customer_customer_type")
        ),
        sa.CheckConstraint(
            "customer_type = 'domestic' OR show_vat_breakdown = 1",
            name=op.f("ck_customer_trade_vat_breakdown"),
        ),
        sa.CheckConstraint(
            "COALESCE(TRIM(first_name),'') <> '' OR COALESCE(TRIM(last_name),'') <> '' "
            "OR COALESCE(TRIM(company_name),'') <> ''",
            name=op.f("ck_customer_has_name"),
        ),
        sa.CheckConstraint(
            "mobile_phone IS NOT NULL OR other_phone IS NOT NULL OR email IS NOT NULL",
            name=op.f("ck_customer_has_contact"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer")),
        sqlite_autoincrement=True,
    )
    for column in (
        "last_name",
        "company_name",
        "mobile_phone_digits",
        "other_phone_digits",
        "email",
        "postcode_compact",
    ):
        op.create_index(op.f(f"ix_customer_{column}"), "customer", [column], unique=False)
    op.create_index(
        "ix_customer_archived_type", "customer", ["is_archived", "customer_type"], unique=False
    )


def downgrade() -> None:
    op.drop_table("customer")
    op.drop_table("settings_change")
    op.drop_table("business_settings")
