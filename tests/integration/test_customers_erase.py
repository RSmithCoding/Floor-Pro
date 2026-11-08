from floorpro.models import Customer
from tests.conftest import make_customer, page_text


def test_erase_dialog(client, session, htmx):
    customer = make_customer(session)
    response = client.get(f"/customers/{customer.id}/erase", headers=htmx)
    assert response.status_code == 200
    text = page_text(response)
    assert "<dialog" in text
    assert "<html" not in text
    assert "Type Jane Smith to confirm" in text
    assert "permanently" in text
    assert 'name="confirm_name"' in text


def test_wrong_name_keeps_customer(client, session, htmx):
    customer = make_customer(session)
    response = client.post(
        f"/customers/{customer.id}/erase", data={"confirm_name": "John Smith"}, headers=htmx
    )
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#modal"
    assert response.headers["HX-Reswap"] == "innerHTML"
    text = page_text(response)
    assert "The name doesn't match." in text
    assert "<dialog" in text
    session.expire_all()
    assert session.get(Customer, customer.id) is not None


def test_matching_name_erases(client, session, htmx):
    customer_id = make_customer(session).id
    response = client.post(
        f"/customers/{customer_id}/erase", data={"confirm_name": "  jane smith "}, headers=htmx
    )
    assert response.status_code == 200
    assert response.headers["HX-Push-Url"] == "/customers"
    text = page_text(response)
    assert "Customer erased" in text
    session.expire_all()
    assert session.get(Customer, customer_id) is None
    assert client.get(f"/customers/{customer_id}").status_code == 404


def test_company_or_person_name_confirms(client, session, htmx):
    for typed in ("acme flooring", "jane smith", "Acme Flooring (Jane Smith)"):
        customer_id = make_customer(session, company_name="Acme Flooring").id
        response = client.post(
            f"/customers/{customer_id}/erase", data={"confirm_name": typed}, headers=htmx
        )
        assert response.status_code == 200, typed
        session.expire_all()
        assert session.get(Customer, customer_id) is None


def test_references_are_never_reused(client, session, htmx):
    customer = make_customer(session)
    client.post(
        f"/customers/{customer.id}/erase", data={"confirm_name": "Jane Smith"}, headers=htmx
    )
    response = client.post(
        "/customers",
        data={"first_name": "Ann", "last_name": "Lee", "email": "ann@example.com"},
        headers=htmx,
    )
    assert "Customer C-00002 added" in page_text(response)


def test_erase_without_htmx_redirects(client, session):
    customer = make_customer(session)
    response = client.post(
        f"/customers/{customer.id}/erase",
        data={"confirm_name": "Jane Smith"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/customers"
    assert "Customer erased" in page_text(client.get("/customers"))


def test_erase_unknown_customer_is_404(client):
    assert client.get("/customers/999/erase").status_code == 404
    assert client.post("/customers/999/erase", data={"confirm_name": "x"}).status_code == 404
