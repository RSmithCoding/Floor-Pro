from sqlalchemy import func, select

from floorpro.models import Customer
from tests.conftest import make_customer, page_text

VALID = {
    "first_name": "Jane",
    "last_name": "Smith",
    "mobile_phone": "07700 900123",
    "address_line1": "1 High Street",
    "town": "Bristol",
    "postcode": "bs1 4dj",
}


def count(session):
    session.expire_all()
    return session.scalar(select(func.count()).select_from(Customer))


def test_create_with_htmx_shows_record_and_toast(client, session, htmx):
    response = client.post("/customers", data=VALID, headers=htmx)
    assert response.status_code == 200
    assert response.headers["HX-Push-Url"] == "/customers/1"
    text = page_text(response)
    assert "C-00001" in text
    assert "BS1 4DJ" in text
    assert "Customer C-00001 added" in text
    assert count(session) == 1


def test_create_without_htmx_redirects_and_flashes_once(client):
    response = client.post("/customers", data=VALID, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/customers/1"

    shown = client.get("/customers/1")
    assert "Customer C-00001 added" in page_text(shown)
    again = client.get("/customers/1")
    assert "Customer C-00001 added" not in page_text(again)


def test_second_customer_gets_next_reference(client, htmx):
    client.post("/customers", data=VALID, headers=htmx)
    response = client.post(
        "/customers",
        data={**VALID, "first_name": "Ann", "mobile_phone": "07700 900999"},
        headers=htmx,
    )
    assert "Customer C-00002 added" in page_text(response)


def test_unrecognised_postcode_saved_with_warning(client, session, htmx):
    response = client.post("/customers", data={**VALID, "postcode": "hello"}, headers=htmx)
    assert response.status_code == 200
    text = page_text(response)
    assert "doesn't look like a UK postcode" in text
    assert "HELLO" in text
    assert count(session) == 1


def test_long_notes_are_saved_in_full(client, session, htmx):
    notes = "Fitting notes. " * 334  # ~5,000 characters
    response = client.post("/customers", data={**VALID, "notes": notes}, headers=htmx)
    assert response.status_code == 200
    assert notes.strip() in page_text(response)
    assert session.get(Customer, 1).notes == notes.strip()


def test_missing_name_is_rejected_and_values_kept(client, session, htmx):
    data = {**VALID, "first_name": "", "last_name": "  "}
    response = client.post("/customers", data=data, headers=htmx)
    assert response.status_code == 422
    text = page_text(response)
    assert "Enter a first name, last name or company name." in text
    assert 'value="07700 900123"' in text
    assert count(session) == 0


def test_company_only_is_accepted(client, session, htmx):
    data = {**VALID, "first_name": "", "last_name": "", "company_name": "Acme Flooring"}
    response = client.post("/customers", data=data, headers=htmx)
    assert response.status_code == 200
    assert count(session) == 1


def test_missing_contact_is_rejected(client, session, htmx):
    data = {**VALID, "mobile_phone": "", "email": ""}
    response = client.post("/customers", data=data, headers=htmx)
    assert response.status_code == 422
    assert "Add a phone number or email address." in page_text(response)
    assert count(session) == 0


def test_invalid_email_and_short_phone_are_rejected(client, session, htmx):
    data = {**VALID, "email": "jane@example", "mobile_phone": "12345"}
    response = client.post("/customers", data=data, headers=htmx)
    assert response.status_code == 422
    text = page_text(response)
    assert "Enter a valid email address" in text
    assert "Enter a phone number with at least 7 digits." in text


def test_too_long_field_is_rejected(client, htmx):
    response = client.post("/customers", data={**VALID, "title": "x" * 21}, headers=htmx)
    assert response.status_code == 422
    assert "at most 20 characters" in page_text(response)


def test_duplicate_phone_warns_then_saves_when_confirmed(client, session, htmx):
    existing = make_customer(session, first_name="Janet", mobile_phone="07700900123")
    response = client.post("/customers", data=VALID, headers=htmx)
    assert response.status_code == 200
    text = page_text(response)
    assert "may already exist" in text
    assert f"/customers/{existing.id}" in text
    assert count(session) == 1

    confirmed = client.post("/customers", data={**VALID, "confirm_duplicate": "1"}, headers=htmx)
    assert confirmed.status_code == 200
    assert "Customer C-00002 added" in page_text(confirmed)
    assert count(session) == 2


def test_duplicate_email_is_case_insensitive(client, session, htmx):
    make_customer(session, email="jane.smith@example.com", mobile_phone=None)
    data = {**VALID, "mobile_phone": "", "email": "Jane.Smith@EXAMPLE.com"}
    response = client.post("/customers", data=data, headers=htmx)
    assert "may already exist" in page_text(response)
    assert count(session) == 1


def test_record_page_and_missing_record(client, session):
    customer = make_customer(session, postcode="bs1 4dj", notes="Prefers mornings")
    response = client.get(f"/customers/{customer.id}")
    assert response.status_code == 200
    text = page_text(response)
    assert "Jane Smith" in text
    assert "C-00001" in text
    assert "Prefers mornings" in text
    assert "Jobs, orders, appointments and invoices" in text
    assert client.get("/customers/999").status_code == 404
