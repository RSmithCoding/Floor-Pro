from fastapi.testclient import TestClient
from sqlalchemy import delete

from floorpro.app import create_app
from floorpro.models import BusinessSettings


def test_dashboard(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    for href in ('href="/"', 'href="/customers"', 'href="/settings"'):
        assert href in html
    assert "Upcoming appointments" in html
    assert "Outstanding invoices" in html
    assert 'aria-current="page"' in html


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.text == "ok"


def test_not_found_page_is_friendly(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert (
        "We couldn&#39;t find that page" in response.text
        or "We couldn't find that page" in response.text
    )
    assert "Traceback" not in response.text
    assert "<html" in response.text


def test_not_found_partial_for_htmx(client, htmx):
    response = client.get("/nope", headers=htmx)
    assert response.status_code == 404
    assert "<html" not in response.text
    assert "find that page" in response.text


def test_server_error_page_hides_details(data_dir):
    app = create_app(data_dir)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internals")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert "Your data is safe" in response.text
    assert "secret internals" not in response.text
    assert "Traceback" not in response.text


def test_missing_settings_row_is_restored_with_notice(data_dir):
    with TestClient(create_app(data_dir)) as client:
        assert client.get("/").status_code == 200
        with client.app.state.sessionmaker.begin() as session:
            session.execute(delete(BusinessSettings))

    with TestClient(create_app(data_dir)) as client:
        first = client.get("/")
        assert "reset to the defaults (GBP, 20% VAT)" in first.text
        second = client.get("/")
        assert "reset to the defaults" not in second.text
        with client.app.state.sessionmaker() as session:
            settings = session.get(BusinessSettings, 1)
            assert settings.currency_code == "GBP"
            assert str(settings.vat_rate) == "20.00"


def test_fresh_install_shows_no_reset_notice(client):
    assert "reset to the defaults" not in client.get("/").text


def test_static_assets_served(client):
    assert client.get("/static/vendor/htmx.min.js").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200
