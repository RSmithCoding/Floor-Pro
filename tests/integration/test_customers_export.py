import json
from datetime import date

from floorpro.models import Customer
from tests.conftest import make_customer

DERIVED = {"id", "mobile_phone_digits", "other_phone_digits", "postcode_compact"}
ADDRESS = {
    "address_line1": "line_1",
    "address_line2": "line_2",
    "town": "town",
    "county": "county",
    "postcode": "postcode",
}
RENAMED = {"is_archived": "archived"}


def full_customer(session):
    return make_customer(
        session,
        title="Mrs",
        company_name=None,
        other_phone="0117 496 0000",
        email="jane.smith@example.com",
        address_line1="1 High Street",
        address_line2="Flat 2",
        town="Bristol",
        county="Avon",
        postcode="BS1 4DJ",
        notes="Prefers morning appointments.",
        marketing_consent=True,
    )


def test_export_headers_and_filename(client, session):
    customer = full_customer(session)
    response = client.get(f"/customers/{customer.id}/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    today = date.today().isoformat()
    assert response.headers["content-disposition"] == (
        f'attachment; filename="FloorPro-customer-C-00001-{today}.json"'
    )


def test_export_contains_every_stored_field(client, session):
    customer = full_customer(session)
    data = json.loads(client.get(f"/customers/{customer.id}/export").text)

    assert data["export"]["format_version"] == 1
    assert data["export"]["produced_by"] == "FloorPro"
    assert data["export"]["exported_at"].endswith("Z")

    exported = data["customer"]
    assert exported["reference"] == "C-00001"
    for column in Customer.__table__.columns.keys():  # noqa: SIM118 (ColumnCollection)
        if column in DERIVED:
            assert column not in exported
        elif column in ADDRESS:
            assert ADDRESS[column] in exported["address"], column
        else:
            assert RENAMED.get(column, column) in exported, column

    assert exported["address"] == {
        "line_1": "1 High Street",
        "line_2": "Flat 2",
        "town": "Bristol",
        "county": "Avon",
        "postcode": "BS1 4DJ",
    }
    assert exported["company_name"] is None
    assert exported["marketing_consent"] is True
    assert exported["archived"] is False
    assert exported["created_at"].endswith("Z")
    assert exported["updated_at"].endswith("Z")
    assert exported["archived_at"] is None
    assert data["related_records"] == {
        "jobs": [],
        "orders": [],
        "appointments": [],
        "invoices": [],
    }


def test_export_keeps_non_ascii_text(client, session):
    customer = make_customer(session, first_name="Zoë", notes="Café floor – oak")
    response = client.get(f"/customers/{customer.id}/export")
    assert "Zoë" in response.text
    assert "Café floor – oak" in response.text


def test_export_unknown_customer_is_404(client):
    assert client.get("/customers/999/export").status_code == 404


# --- Desktop: native save dialog instead of navigating to the file -------------------------


class FakeSaver:
    """Stands in for the native Save dialog that the desktop launcher provides."""

    def __init__(self, folder, cancel=False):
        self.folder, self.cancel, self.calls = folder, cancel, []

    def __call__(self, filename: str, data: bytes):
        self.calls.append(filename)
        if self.cancel:
            return None
        path = self.folder / filename
        path.write_bytes(data)
        return path


def test_desktop_export_saves_via_dialog(client, app, session, htmx, tmp_path):
    saver = FakeSaver(tmp_path)
    app.state.save_file = saver
    customer = full_customer(session)
    response = client.post(f"/customers/{customer.id}/export/save", headers=htmx)
    assert response.status_code == 200
    today = date.today().isoformat()
    filename = f"FloorPro-customer-C-00001-{today}.json"
    assert saver.calls == [filename]
    assert f"Exported to {filename}" in response.text
    assert "HX-Push-Url" not in response.headers  # the page stays where it is
    saved = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
    assert saved["customer"]["reference"] == "C-00001"


def test_desktop_export_cancelled(client, app, session, htmx, tmp_path):
    app.state.save_file = FakeSaver(tmp_path, cancel=True)
    customer = full_customer(session)
    response = client.post(f"/customers/{customer.id}/export/save", headers=htmx)
    assert response.status_code == 200
    assert "Export cancelled" in response.text
    assert list(tmp_path.glob("*.json")) == []


def test_desktop_export_needs_the_desktop_window(client, session, htmx):
    customer = full_customer(session)
    response = client.post(f"/customers/{customer.id}/export/save", headers=htmx)
    assert response.status_code == 404


def test_export_control_matches_mode(client, app, session, tmp_path):
    customer = full_customer(session)
    browser_page = client.get(f"/customers/{customer.id}").text
    assert f'href="/customers/{customer.id}/export"' in browser_page
    assert "/export/save" not in browser_page

    app.state.save_file = FakeSaver(tmp_path)
    desktop_page = client.get(f"/customers/{customer.id}").text
    assert f'hx-post="/customers/{customer.id}/export/save"' in desktop_page
    assert f'href="/customers/{customer.id}/export"' not in desktop_page
