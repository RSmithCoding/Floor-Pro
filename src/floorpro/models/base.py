"""Declarative base and column types shared by all models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from floorpro.domain.money import (
    bp_to_percent,
    from_minor_units,
    percent_to_bp,
    to_minor_units,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Money(TypeDecorator[Decimal]):
    """``Decimal`` in code, integer minor units (pence) in the database."""

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else to_minor_units(value)

    def process_result_value(self, value, dialect):
        return None if value is None else from_minor_units(value)


class Percent(TypeDecorator[Decimal]):
    """``Decimal`` percentage in code, integer basis points in the database."""

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else percent_to_bp(value)

    def process_result_value(self, value, dialect):
        return None if value is None else bp_to_percent(value)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC ``datetime`` in code, naive UTC in the database."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use timezone-aware UTC")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)
