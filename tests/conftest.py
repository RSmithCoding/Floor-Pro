from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from floorpro.app import create_app
from floorpro.models import Customer

HTMX = {"HX-Request": "true"}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORPRO_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def app(data_dir):
    return create_app(data_dir)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(client, app):
    with app.state.sessionmaker() as db_session:
        yield db_session


@pytest.fixture
def htmx():
    return dict(HTMX)


def make_customer(session, **overrides) -> Customer:
    """Insert a valid domestic customer (derived columns computed) and commit."""
    from floorpro.domain.validation import normalise_postcode, phone_digits, postcode_compact

    now = datetime.now(UTC)
    values = dict(
        customer_type="domestic",
        show_vat_breakdown=False,
        first_name="Jane",
        last_name="Smith",
        mobile_phone="07700 900123",
        marketing_consent=False,
        is_archived=False,
        created_at=now,
        updated_at=now,
    )
    values.update(overrides)
    for field in ("mobile_phone", "other_phone"):
        values[f"{field}_digits"] = phone_digits(values[field]) if values.get(field) else None
    if values.get("postcode"):
        values["postcode"] = normalise_postcode(values["postcode"])[0]
        values["postcode_compact"] = postcode_compact(values["postcode"])
    customer = Customer(**values)
    session.add(customer)
    session.commit()
    return customer


def page_text(response) -> str:
    """Response HTML with entities decoded, so assertions can use plain apostrophes."""
    import html

    return html.unescape(response.text)
