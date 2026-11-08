from floorpro.models import Customer
from tests.conftest import make_customer, page_text


def test_archive_dialog(client, session, htmx):
    customer = make_customer(session)
    response = client.get(f"/customers/{customer.id}/archive", headers=htmx)
    assert response.status_code == 200
    text = page_text(response)
    assert "<dialog" in text
    assert "<html" not in text
    assert "Archive Jane Smith?" in text
    assert "you can restore them at any time" in text
    assert f'action="/customers/{customer.id}/archive"' in text


def test_archive_and_restore(client, session, htmx):
    customer = make_customer(session)

    archived = client.post(f"/customers/{customer.id}/archive", headers=htmx)
    assert archived.status_code == 200
    assert archived.headers["HX-Push-Url"] == f"/customers/{customer.id}"
    text = page_text(archived)
    assert "Customer archived" in text
    assert "Archived" in text
    assert "Restore" in text
    session.expire_all()
    saved = session.get(Customer, customer.id)
    assert saved.is_archived is True
    assert saved.archived_at is not None

    listing = page_text(client.get("/customers", headers=htmx))
    assert "Jane Smith" not in listing
    assert "Jane Smith" in page_text(client.get("/customers?archived=1", headers=htmx))

    restored = client.post(f"/customers/{customer.id}/restore", headers=htmx)
    assert restored.status_code == 200
    assert "Customer restored" in page_text(restored)
    session.expire_all()
    saved = session.get(Customer, customer.id)
    assert saved.is_archived is False
    assert saved.archived_at is None
    assert "Jane Smith" in page_text(client.get("/customers", headers=htmx))


def test_archived_customer_still_triggers_duplicate_warning(client, session, htmx):
    make_customer(session, is_archived=True, mobile_phone="07700 900123")
    response = client.post(
        "/customers",
        data={"first_name": "Jane", "last_name": "Smith", "mobile_phone": "07700900123"},
        headers=htmx,
    )
    text = page_text(response)
    assert "may already exist" in text
    assert "(archived)" in text


def test_archive_unknown_customer_is_404(client):
    assert client.get("/customers/999/archive").status_code == 404
    assert client.post("/customers/999/archive").status_code == 404
    assert client.post("/customers/999/restore").status_code == 404
