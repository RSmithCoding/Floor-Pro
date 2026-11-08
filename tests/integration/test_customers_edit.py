import re
import time

from floorpro.models import Customer
from tests.conftest import make_customer, page_text

FORM = {
    "first_name": "Jane",
    "last_name": "Smith",
    "mobile_phone": "07700 900123",
    "postcode": "BS1 4DJ",
}


def test_edit_form_is_prefilled(client, session):
    customer = make_customer(session, postcode="bs1 4dj", notes="Prefers mornings")
    response = client.get(f"/customers/{customer.id}/edit")
    assert response.status_code == 200
    text = page_text(response)
    assert "Edit customer" in text
    assert f'action="/customers/{customer.id}"' in text
    assert re.search(r'name="first_name"[^>]*value="Jane"', text)
    assert re.search(r'name="postcode"[^>]*value="BS1 4DJ"', text)
    assert "Prefers mornings" in text


def test_update_saves_and_shows_toast(client, session, htmx):
    customer = make_customer(session)
    before = customer.updated_at
    time.sleep(0.01)
    response = client.post(
        f"/customers/{customer.id}", data={**FORM, "mobile_phone": "07700 111222"}, headers=htmx
    )
    assert response.status_code == 200
    assert response.headers["HX-Push-Url"] == f"/customers/{customer.id}"
    text = page_text(response)
    assert "Customer updated" in text
    assert "07700 111222" in text
    session.expire_all()
    saved = session.get(Customer, customer.id)
    assert saved.mobile_phone == "07700 111222"
    assert saved.mobile_phone_digits == "07700111222"
    assert saved.updated_at > before
    assert saved.created_at == customer.created_at


def test_update_without_htmx_redirects(client, session):
    customer = make_customer(session)
    response = client.post(f"/customers/{customer.id}", data=FORM, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/customers/{customer.id}"


def test_update_validation_error(client, session, htmx):
    customer = make_customer(session)
    response = client.post(
        f"/customers/{customer.id}", data={**FORM, "first_name": "", "last_name": ""}, headers=htmx
    )
    assert response.status_code == 422
    assert "Enter a first name, last name or company name." in page_text(response)
    session.expire_all()
    assert session.get(Customer, customer.id).first_name == "Jane"


def test_duplicate_check_only_when_phone_or_email_changes(client, session, htmx):
    make_customer(session, first_name="Janet", mobile_phone="07700 999000")
    customer = make_customer(session, mobile_phone="07700 999000")

    notes_only = client.post(
        f"/customers/{customer.id}",
        data={**FORM, "mobile_phone": "07700 999000", "notes": "New note"},
        headers=htmx,
    )
    assert "may already exist" not in page_text(notes_only)
    assert "Customer updated" in page_text(notes_only)

    other = make_customer(session, first_name="Ann", mobile_phone="07700 555444")
    changed = client.post(
        f"/customers/{other.id}",
        data={**FORM, "first_name": "Ann", "mobile_phone": "07700999000"},
        headers=htmx,
    )
    assert "may already exist" in page_text(changed)
    session.expire_all()
    assert session.get(Customer, other.id).mobile_phone == "07700 555444"


def test_edit_unknown_customer_is_404(client):
    assert client.get("/customers/999/edit").status_code == 404
    assert client.post("/customers/999", data=FORM).status_code == 404
