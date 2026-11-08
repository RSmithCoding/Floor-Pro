"""Principle IV: everything is bundled locally, and custom JavaScript stays tiny."""

import re

from floorpro.paths import resource_path
from tests.conftest import make_customer

PAGES = ["/", "/customers", "/customers/new", "/settings", "/settings/history"]


def test_no_external_urls_in_any_page(client, session):
    customer = make_customer(session)
    for path in [*PAGES, f"/customers/{customer.id}", f"/customers/{customer.id}/edit"]:
        html = client.get(path).text
        external = re.findall(r'(?:src|href)="(https?://[^"]*)"', html)
        assert external == [], f"{path} loads {external}"


def test_stylesheet_has_no_external_urls():
    css = resource_path("static/css/input.css").read_text(encoding="utf-8")
    assert "http://" not in css and "https://" not in css


def test_custom_javascript_stays_small():
    lines = resource_path("static/js/app.js").read_text(encoding="utf-8").splitlines()
    assert len([line for line in lines if line.strip()]) < 40


def test_bundled_assets_are_served(client):
    for path in (
        "/static/vendor/htmx.min.js",
        "/static/js/app.js",
        "/static/fonts/InterVariable.woff2",
    ):
        assert client.get(path).status_code == 200, path
