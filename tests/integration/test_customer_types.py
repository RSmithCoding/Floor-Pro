"""Spec scenarios 4.1 to 4.5: domestic and trade customers."""

import re

from floorpro.models import Customer
from tests.conftest import make_customer, page_text

BASE = {"first_name": "Jane", "last_name": "Smith", "email": "jane@example.com"}


def saved(session, customer_id) -> Customer:
    session.expire_all()
    return session.get(Customer, customer_id)


def create(client, htmx, **data) -> int:
    response = client.post("/customers", data={**BASE, **data}, headers=htmx)
    assert response.status_code == 200, response.text
    return int(response.headers["HX-Push-Url"].rsplit("/", 1)[1])


# --- Saving types --------------------------------------------------------------------------


def test_new_customer_defaults_to_domestic_without_breakdown(client, session, htmx):
    customer = saved(session, create(client, htmx))
    assert customer.customer_type == "domestic"
    assert customer.show_vat_breakdown is False


def test_trade_forces_breakdown_on(client, session, htmx):
    customer = saved(session, create(client, htmx, customer_type="trade", vat_fields_present="1"))
    assert customer.customer_type == "trade"
    assert customer.show_vat_breakdown is True


def test_domestic_can_opt_in(client, session, htmx):
    customer_id = create(client, htmx, show_vat_breakdown="on", vat_fields_present="1")
    assert saved(session, customer_id).show_vat_breakdown is True


def test_domestic_to_trade_locks_breakdown_on(client, session, htmx):
    customer = make_customer(session, email="jane@example.com")
    response = client.post(
        f"/customers/{customer.id}",
        data={**BASE, "customer_type": "trade", "vat_fields_present": "1"},
        headers=htmx,
    )
    assert response.status_code == 200
    assert saved(session, customer.id).show_vat_breakdown is True


def test_trade_to_domestic_keeps_breakdown_until_unticked(client, session, htmx):
    customer = make_customer(
        session, customer_type="trade", show_vat_breakdown=True, email="jane@example.com"
    )
    client.post(
        f"/customers/{customer.id}", data={**BASE, "customer_type": "domestic"}, headers=htmx
    )
    after_switch = saved(session, customer.id)
    assert after_switch.customer_type == "domestic"
    assert after_switch.show_vat_breakdown is True

    client.post(
        f"/customers/{customer.id}",
        data={**BASE, "customer_type": "domestic", "vat_fields_present": "1"},
        headers=htmx,
    )
    assert saved(session, customer.id).show_vat_breakdown is False


def test_invalid_type_rejected(client, htmx):
    response = client.post("/customers", data={**BASE, "customer_type": "wholesale"}, headers=htmx)
    assert response.status_code == 422


# --- Form partials -------------------------------------------------------------------------


def test_vat_fields_partial_for_trade(client, htmx):
    response = client.get(
        "/customers/form/vat-fields",
        params={"customer_type": "trade", "original_type": "domestic"},
        headers=htmx,
    )
    assert response.status_code == 200
    text = page_text(response)
    assert "<html" not in text
    checkbox = re.search(r'<input id="show_vat_breakdown"[^>]*>', text).group(0)
    assert " checked" in checkbox
    assert " disabled" in checkbox
    assert '<input type="hidden" name="show_vat_breakdown" value="on">' in text
    assert "Always shown for trade customers" in text


def test_vat_fields_partial_for_domestic(client, htmx):
    response = client.get(
        "/customers/form/vat-fields",
        params={"customer_type": "domestic", "show_vat_breakdown": "on", "original_type": "trade"},
        headers=htmx,
    )
    text = page_text(response)
    checkbox = re.search(r'<input id="show_vat_breakdown"[^>]*>', text).group(0)
    assert " checked" in checkbox
    assert " disabled" not in checkbox
    assert "insurance jobs" in text
    assert 'name="vat_fields_present" value="1"' in text


def test_trade_form_puts_company_name_first(client):
    trade = page_text(client.get("/customers/new", params={"customer_type": "trade"}))
    assert trade.index('name="company_name"') < trade.index('name="first_name"')
    assert re.search(r'name="customer_type" value="trade"[^>]*checked', trade)

    domestic = page_text(client.get("/customers/new"))
    assert domestic.index('name="first_name"') < domestic.index('name="company_name"')


def test_type_change_also_reorders_name_fields(client, htmx):
    response = client.get(
        "/customers/form/vat-fields",
        params={"customer_type": "trade", "first_name": "Jane", "company_name": "Acme"},
        headers=htmx,
    )
    text = page_text(response)
    assert 'id="name-fields" hx-swap-oob="true"' in text
    assert text.index('name="company_name"') < text.index('name="first_name"')
    assert re.search(r'name="company_name"[^>]*value="Acme"', text)


# --- List ----------------------------------------------------------------------------------


def test_list_filters_by_type_and_shows_badges(client, session, htmx):
    make_customer(session, first_name="Dora", last_name="Domestic")
    make_customer(
        session,
        first_name="Ted",
        last_name="Trade",
        customer_type="trade",
        show_vat_breakdown=True,
    )
    trade_only = page_text(client.get("/customers", params={"type": "trade"}, headers=htmx))
    assert "Ted Trade" in trade_only
    assert "Dora Domestic" not in trade_only

    domestic_only = page_text(client.get("/customers", params={"type": "domestic"}, headers=htmx))
    assert "Dora Domestic" in domestic_only
    assert "Ted Trade" not in domestic_only

    everyone = page_text(client.get("/customers", headers=htmx))
    rows = re.findall(r"<tr data-customer-row.*?</tr>", everyone, re.S)
    assert len(rows) == 2
    assert all(("Trade</span>" in row) or ("Domestic</span>" in row) for row in rows)

    page = page_text(client.get("/customers"))
    for value in ("all", "domestic", "trade"):
        assert re.search(rf'name="type" value="{value}"', page)
