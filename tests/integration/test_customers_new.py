import re

import pytest

from tests.conftest import page_text


def field_value(html: str, name: str) -> str | None:
    match = re.search(rf'name="{name}"[^>]*value="([^"]*)"', html)
    return match.group(1) if match else None


def test_blank_form(client):
    response = client.get("/customers/new")
    assert response.status_code == 200
    text = page_text(response)
    assert "<html" in text
    assert "Add customer" in text
    assert field_value(text, "first_name") == ""
    assert re.search(r'name="customer_type" value="domestic"[^>]*checked', text)


@pytest.mark.parametrize(
    "prefill, expected",
    [
        ("07700 900123", {"mobile_phone": "07700 900123"}),
        ("jane@example.com", {"email": "jane@example.com"}),
        ("Jane Smith", {"first_name": "Jane", "last_name": "Smith"}),
        ("Acme", {"first_name": "Acme"}),
    ],
)
def test_prefill(client, prefill, expected):
    text = page_text(client.get("/customers/new", params={"prefill": prefill}))
    for name, value in expected.items():
        assert field_value(text, name) == value


def test_htmx_returns_form_partial(client, htmx):
    response = client.get("/customers/new", headers=htmx)
    assert response.status_code == 200
    assert "<html" not in response.text
    assert 'name="first_name"' in response.text
