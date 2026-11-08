from fastapi.testclient import TestClient

from floorpro.app import create_app
from tests.conftest import make_customer, page_text


def results(client, htmx, **params):
    response = client.get("/customers", params=params, headers=htmx)
    assert response.status_code == 200
    return page_text(response)


def test_search_by_phone_ignores_spacing(client, session, htmx):
    make_customer(session, mobile_phone="07700 900123")
    make_customer(session, first_name="Bob", last_name="Other", mobile_phone="07700 111222")
    text = results(client, htmx, q="07700900123")
    assert "Jane Smith" in text
    assert "Bob Other" not in text


def test_search_by_postcode(client, session, htmx):
    make_customer(session, postcode="SW1A 1AA")
    make_customer(session, first_name="Bob", last_name="Other", postcode="BS1 4DJ")
    text = results(client, htmx, q="SW1A")
    assert "Jane Smith" in text
    assert "Bob Other" not in text
    assert "Jane Smith" in results(client, htmx, q="sw1a1a")


def test_search_by_name_company_email_and_reference(client, session, htmx):
    make_customer(session, last_name="Smithson")
    make_customer(
        session,
        first_name=None,
        last_name=None,
        company_name="Acme Flooring",
        mobile_phone=None,
        email="Accounts@Acme.example",
    )
    assert "Jane Smithson" in results(client, htmx, q="smiths")
    assert "Acme Flooring" in results(client, htmx, q="acme fl")
    assert "Acme Flooring" in results(client, htmx, q="accounts@acme")
    for ref in ("c-00001", "C1", "c1"):
        text = results(client, htmx, q=ref)
        assert "Jane Smithson" in text
        assert "Acme Flooring" not in text


def test_archived_customers_hidden_unless_requested(client, session, htmx):
    make_customer(session, first_name="Active")
    make_customer(session, first_name="Archived", is_archived=True)
    default = results(client, htmx)
    assert "Active Smith" in default
    assert "Archived Smith" not in default
    assert "Archived Smith" in results(client, htmx, archived="1")


def test_sorting(client, session, htmx):
    make_customer(session, first_name="Zed", last_name="Adams")
    make_customer(session, first_name="Amy", last_name="Young")
    by_name = results(client, htmx, sort="name", dir="asc")
    assert by_name.index("Zed Adams") < by_name.index("Amy Young")
    by_name_desc = results(client, htmx, sort="name", dir="desc")
    assert by_name_desc.index("Amy Young") < by_name_desc.index("Zed Adams")
    by_ref_desc = results(client, htmx, sort="reference", dir="desc")
    assert by_ref_desc.index("Amy Young") < by_ref_desc.index("Zed Adams")
    by_created = results(client, htmx, sort="created", dir="asc")
    assert by_created.index("Zed Adams") < by_created.index("Amy Young")


def test_partial_vs_full_page(client, session, htmx):
    make_customer(session)
    partial = client.get("/customers", params={"q": "jane"}, headers=htmx)
    assert "<html" not in partial.text
    assert "Jane Smith" in partial.text
    full = client.get("/customers", params={"q": "jane"})
    assert "<html" in full.text
    assert "Jane Smith" in full.text


def test_no_results_offers_to_add(client, session, htmx):
    make_customer(session)
    text = results(client, htmx, q="zzz")
    assert "No customers found" in text
    assert "Add 'zzz' as a new customer" in text
    assert "/customers/new?prefill=zzz" in text


def test_results_capped_at_50(client, session, htmx):
    for i in range(60):
        make_customer(session, first_name=f"Person{i:02d}", mobile_phone=f"07700 9{i:05d}")
    text = results(client, htmx, q="person")
    assert "Showing 50 of 60" in text
    assert text.count("data-customer-row") == 50


def test_customers_survive_restart(data_dir, htmx):
    with TestClient(create_app(data_dir)) as client:
        for name in ("Ann", "Bob", "Cat"):
            client.post(
                "/customers",
                data={"first_name": name, "last_name": "Lee", "email": f"{name}@example.com"},
                headers=htmx,
            )
    with TestClient(create_app(data_dir)) as client:
        text = page_text(client.get("/customers"))
        for name in ("Ann Lee", "Bob Lee", "Cat Lee"):
            assert name in text
        assert "Bob@example.com" in text
