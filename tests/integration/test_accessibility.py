"""T073: automated accessibility checks across every page and dialog.

Checks what can be verified from the HTML: every form control has a label, every
aria-describedby/aria-labelledby points at a real element, errors are linked to their
fields, the toast region is announced, and dialogs are native <dialog> elements (which
trap focus and close on Escape when opened with showModal()).
"""

from html.parser import HTMLParser

import pytest

from tests.conftest import make_customer

LABELLED_INPUT_TYPES = {
    "text",
    "email",
    "tel",
    "search",
    "checkbox",
    "radio",
    "number",
    "password",
    "file",
    "",
}


class PageAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.label_for: set[str] = set()
        self.controls: list[dict] = []
        self.references: list[tuple[str, str]] = []
        self.label_depth = 0
        self.dialogs: list[dict] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for attr in ("aria-describedby", "aria-labelledby"):
            for ref in (a.get(attr) or "").split():
                self.references.append((attr, ref))
        if tag == "label":
            self.label_depth += 1
            if "for" in a:
                self.label_for.add(a["for"])
        if tag in ("input", "select", "textarea"):
            kind = a.get("type", "")
            if tag != "input" or kind in LABELLED_INPUT_TYPES:
                self.controls.append({**a, "_tag": tag, "_wrapped": self.label_depth > 0})
        if tag == "dialog":
            self.dialogs.append(a)

    def handle_endtag(self, tag):
        if tag == "label":
            self.label_depth -= 1


def audit(html: str) -> PageAudit:
    parser = PageAudit()
    parser.feed(html)
    return parser


def assert_accessible(html: str, where: str) -> None:
    page = audit(html)
    for control in page.controls:
        labelled = (
            control["_wrapped"] or control.get("id") in page.label_for or control.get("aria-label")
        )
        assert labelled, f"{where}: unlabelled {control['_tag']} name={control.get('name')}"
    for attr, ref in page.references:
        assert ref in page.ids, f"{where}: {attr} points at missing id {ref!r}"
    for dialog in page.dialogs:
        labelledby = dialog.get("aria-labelledby")
        assert labelledby and labelledby in page.ids, f"{where}: dialog has no title"


@pytest.fixture
def customer(session):
    return make_customer(session, postcode="BS1 4DJ", email="jane@example.com")


def test_pages_are_accessible(client, customer):
    paths = [
        "/",
        "/customers",
        "/customers?q=zzz",
        "/customers/new",
        "/customers/new?customer_type=trade",
        "/settings",
        "/settings/history",
        f"/customers/{customer.id}",
        f"/customers/{customer.id}/edit",
        "/nope",
    ]
    for path in paths:
        assert_accessible(client.get(path).text, path)


def test_forms_with_errors_link_messages_to_fields(client, htmx):
    customer_errors = client.post(
        "/customers", data={"email": "bad", "mobile_phone": "123"}, headers=htmx
    )
    assert_accessible(customer_errors.text, "customer form errors")
    assert 'aria-describedby="email-error"' in customer_errors.text
    assert 'aria-invalid="true"' in customer_errors.text

    settings_errors = client.post(
        "/settings",
        data={
            "currency_code": "GBP",
            "vat_registered": "on",
            "vat_rate": "150",
            "price_entry_mode": "inc_vat",
        },
        headers=htmx,
    )
    assert_accessible(settings_errors.text, "settings form errors")
    assert 'aria-describedby="vat_rate-error"' in settings_errors.text


def test_dialogs_are_accessible(client, customer, htmx):
    staged = client.post(
        "/settings",
        data={
            "currency_code": "EUR",
            "vat_registered": "on",
            "vat_rate": "20",
            "price_entry_mode": "inc_vat",
        },
        headers=htmx,
    )
    for where, html in [
        ("settings confirm", staged.text),
        ("archive", client.get(f"/customers/{customer.id}/archive", headers=htmx).text),
        ("erase", client.get(f"/customers/{customer.id}/erase", headers=htmx).text),
    ]:
        assert "<dialog" in html, where
        assert_accessible(html, where)


def test_live_region_and_language(client):
    html = client.get("/").text
    assert '<html lang="en-GB"' in html
    assert 'id="toasts" aria-live="polite"' in html


def test_focus_styles_defined():
    from floorpro.paths import resource_path

    css = resource_path("static/css/input.css").read_text(encoding="utf-8")
    assert ":focus-visible" in css


# --- Backups and recovery (feature 002) ------------------------------------------------------


def test_backup_pages_are_accessible(client, data_dir):
    from floorpro.services import backup_service

    assert_accessible(client.get("/backups").text, "/backups (no password)")
    backup_service.set_password("correct horse battery")
    client.post("/backups")
    client.post("/backups")
    assert_accessible(client.get("/backups").text, "/backups (with backups)")
    assert_accessible(client.get("/").text, "/ (backup card)")


def test_recovery_page_is_accessible(data_dir):
    from fastapi.testclient import TestClient

    from floorpro.app import create_app

    with TestClient(create_app(data_dir)):
        pass
    with open(data_dir / "floorpro.db", "r+b") as fh:
        fh.write(b"\x00garbage!" * 12)
    with TestClient(create_app(data_dir)) as client:
        html = client.get("/recovery").text
        assert_accessible(html, "/recovery")
        assert '<html lang="en-GB"' in html


def test_backup_dialogs_are_accessible(client, data_dir, htmx):
    from floorpro.services import backup_service

    backup_service.set_password("correct horse battery")
    client.post("/backups")
    client.post("/backups")
    names = sorted(p.name for p in (data_dir / "backups").glob("*.fpbackup"))
    for where, url in [
        ("restore", f"/backups/local/{names[0]}/restore"),
        ("delete", f"/backups/local/{names[0]}/delete"),
        ("change password", "/backups/password/change"),
    ]:
        html = client.get(url, headers=htmx).text
        assert "<dialog" in html, where
        assert_accessible(html, where)


def test_backup_errors_are_linked_to_fields(client, data_dir, htmx):
    from floorpro.services import backup_service

    html = client.post(
        "/backups/password", data={"password": "short", "password_confirm": "x"}, headers=htmx
    ).text
    assert_accessible(html, "set password errors")
    assert 'aria-describedby="password-hint password-error"' in html
    assert 'aria-describedby="password_confirm-error"' in html

    backup_service.set_password("correct horse battery")
    client.post("/backups")
    name = next((data_dir / "backups").glob("*.fpbackup")).name
    html = client.post(f"/backups/local/{name}/restore", data={"confirm": "no"}, headers=htmx).text
    assert_accessible(html, "restore confirm errors")
    assert 'aria-describedby="confirm-error"' in html


def test_progress_messages_are_announced(client, data_dir, htmx):
    from floorpro.services import backup_service

    backup_service.set_password("correct horse battery")
    client.post("/backups")
    page = client.get("/backups").text
    assert 'aria-live="polite"><svg' in page and "Backing up…" in page
    name = next((data_dir / "backups").glob("*.fpbackup")).name
    dialog = client.get(f"/backups/local/{name}/restore", headers=htmx).text
    progress = dialog.split('id="restore-progress"', 1)[1].split("</p>", 1)[0]
    assert 'aria-live="polite"' in progress
    assert "Restoring… this can take up to 30 seconds" in progress
