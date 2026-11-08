import re
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from floorpro.app import create_app
from floorpro.models import BusinessSettings, SettingsChange
from floorpro.templating import templates
from tests.conftest import page_text

DEFAULT_FORM = {
    "currency_code": "GBP",
    "vat_registered": "on",
    "vat_rate": "20",
    "vat_number": "",
    "price_entry_mode": "inc_vat",
}


def stage(client, htmx, **changes):
    data = {**DEFAULT_FORM, **changes}
    data = {k: v for k, v in data.items() if v is not None}
    return client.post("/settings", data=data, headers=htmx)


def hidden_fields(html: str) -> dict[str, str]:
    dialog = html[html.index("<dialog") :]
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', dialog))


def stage_and_confirm(client, htmx, **changes):
    staged = stage(client, htmx, **changes)
    assert staged.status_code == 200, staged.text
    return client.post("/settings/confirm", data=hidden_fields(staged.text), headers=htmx)


def changes(session):
    session.expire_all()
    return list(session.scalars(select(SettingsChange).order_by(SettingsChange.id)))


def current(session) -> BusinessSettings:
    session.expire_all()
    return session.get(BusinessSettings, 1)


# --- Defaults ------------------------------------------------------------------------------


def test_defaults_shown(client):
    response = client.get("/settings")
    assert response.status_code == 200
    text = page_text(response)
    assert re.search(r'<option value="GBP"[^>]*selected', text)
    assert re.search(r'name="vat_registered"[^>]*checked', text)
    assert re.search(r'name="vat_rate"[^>]*value="20"', text)
    assert re.search(r'name="price_entry_mode" value="inc_vat"[^>]*checked', text)
    assert "Prices include VAT" in text
    assert 'aria-current="page"' in text


# --- Confirm flow --------------------------------------------------------------------------


def test_change_requires_confirmation_then_saves(client, session, htmx):
    staged = stage(client, htmx, vat_rate="17.5")
    assert staged.status_code == 200
    text = page_text(staged)
    assert "<dialog" in text
    assert "20% → 17.5%" in text
    assert "apply to new quotes and invoices only" in text
    assert current(session).vat_rate == Decimal("20.00")
    assert changes(session) == []

    confirmed = client.post("/settings/confirm", data=hidden_fields(staged.text), headers=htmx)
    assert confirmed.status_code == 200
    assert confirmed.headers["HX-Push-Url"] == "/settings"
    assert "Settings saved" in page_text(confirmed)
    assert current(session).vat_rate == Decimal("17.50")
    rows = changes(session)
    assert [(r.field, r.old_value, r.new_value) for r in rows] == [("vat_rate", "20.00", "17.50")]


def test_several_changes_share_a_change_set(client, session, htmx):
    stage_and_confirm(client, htmx, currency_code="EUR", vat_rate="17.5", price_entry_mode="ex_vat")
    rows = changes(session)
    assert {r.field for r in rows} == {"currency_code", "vat_rate", "price_entry_mode"}
    assert len({r.change_set_id for r in rows}) == 1
    assert len({r.changed_at for r in rows}) == 1


def test_confirm_without_htmx_redirects_with_flash(client, session, htmx):
    staged = stage(client, htmx, vat_rate="15")
    response = client.post(
        "/settings/confirm", data=hidden_fields(staged.text), follow_redirects=False
    )
    assert response.status_code == 303
    assert "Settings saved" in page_text(client.get("/settings"))


# --- Validation and special cases ----------------------------------------------------------


def test_invalid_rates_rejected(client, htmx):
    for bad in ("-5", "150", "abc", "12.345"):
        response = stage(client, htmx, vat_rate=bad)
        assert response.status_code == 422
        assert response.headers["HX-Retarget"] == "#settings-form"
        assert response.headers["HX-Reswap"] == "outerHTML"
        assert "Enter a VAT rate between 0 and 100, with up to two decimal places." in page_text(
            response
        )


def test_invalid_vat_number_and_currency_rejected(client, htmx):
    response = stage(client, htmx, vat_number="GB12")
    assert response.status_code == 422
    assert "Enter a UK VAT number, for example GB123456789." in page_text(response)
    response = stage(client, htmx, currency_code="XYZ")
    assert response.status_code == 422
    assert "Choose a currency from the list." in page_text(response)


def test_vat_number_normalised(client, session, htmx):
    stage_and_confirm(client, htmx, vat_number="gb 123 4567 89")
    assert current(session).vat_number == "GB123456789"


def test_not_vat_registered_makes_rate_and_number_optional(client, session, htmx):
    staged = stage(client, htmx, vat_registered=None, vat_rate="", vat_number="")
    assert staged.status_code == 200
    assert "VAT registered: Yes → No" in page_text(staged)
    client.post("/settings/confirm", data=hidden_fields(staged.text), headers=htmx)
    settings = current(session)
    assert settings.vat_registered is False
    assert settings.vat_rate == Decimal("20.00")  # kept for when they register again


def test_currency_change_updates_money_filter(client, session, htmx):
    stage_and_confirm(client, htmx, currency_code="EUR")
    rendered = templates.env.from_string("{{ amount|money }}").render(
        amount=Decimal("1234.5"), settings=current(session)
    )
    assert rendered == "€1,234.50"
    assert re.search(r'<option value="EUR"[^>]*selected', page_text(client.get("/settings")))


def test_price_entry_mode_change_recorded(client, session, htmx):
    staged = stage(client, htmx, price_entry_mode="ex_vat")
    assert "Prices include VAT → Prices exclude VAT" in page_text(staged)
    client.post("/settings/confirm", data=hidden_fields(staged.text), headers=htmx)
    assert [(r.field, r.new_value) for r in changes(session)] == [("price_entry_mode", "ex_vat")]


def test_unchanged_post_says_nothing_to_change(client, session, htmx):
    response = stage(client, htmx)
    assert response.status_code == 200
    assert "Nothing to change" in page_text(response)
    assert "<dialog" not in response.text
    assert changes(session) == []


def test_stale_token_is_rejected(client, session, htmx):
    stale = stage(client, htmx, vat_rate="17.5")
    stage_and_confirm(client, htmx, currency_code="USD")
    response = client.post("/settings/confirm", data=hidden_fields(stale.text), headers=htmx)
    assert response.status_code == 409
    assert "changed since" in page_text(response)
    assert current(session).vat_rate == Decimal("20.00")


def test_tampered_values_are_rejected(client, session, htmx):
    staged = stage(client, htmx, vat_rate="17.5")
    fields = hidden_fields(staged.text)
    fields["vat_rate"] = "5"
    response = client.post("/settings/confirm", data=fields, headers=htmx)
    assert response.status_code == 409
    assert current(session).vat_rate == Decimal("20.00")


# --- Persistence and history ---------------------------------------------------------------


def test_settings_persist_across_restart(data_dir, htmx):
    with TestClient(create_app(data_dir)) as client:
        stage_and_confirm(client, htmx, currency_code="USD", vat_rate="12.5")
    with TestClient(create_app(data_dir)) as client:
        text = page_text(client.get("/settings"))
        assert re.search(r'<option value="USD"[^>]*selected', text)
        assert re.search(r'name="vat_rate"[^>]*value="12.5"', text)


def test_history_lists_newest_first(client, htmx):
    stage_and_confirm(client, htmx, vat_rate="17.5")
    stage_and_confirm(client, htmx, vat_rate="17.5", currency_code="EUR")
    response = client.get("/settings/history")
    assert response.status_code == 200
    text = page_text(response)
    assert text.index("Currency") < text.index("VAT rate")
    assert "20% → 17.5%" not in text  # history shows old and new in separate columns
    assert "GBP (£)" in text and "EUR (€)" in text
    assert "Change history" in page_text(client.get("/settings"))


# --- Form behaviour ------------------------------------------------------------------------


def test_vat_fields_partial(client, htmx):
    off = client.get(
        "/settings/form/vat-fields",
        params={"vat_rate": "20", "vat_number": "GB123456789"},
        headers=htmx,
    )
    assert off.status_code == 200
    text = page_text(off)
    assert "Not applicable — business isn't VAT registered" in text
    assert re.search(r'id="vat_rate"[^>]*\sdisabled(?=[\s>])', text)
    assert '<input type="hidden" name="vat_rate" value="20">' in text
    assert '<input type="hidden" name="vat_number" value="GB123456789">' in text

    on = client.get(
        "/settings/form/vat-fields",
        params={"vat_registered": "on", "vat_rate": "20", "vat_number": ""},
        headers=htmx,
    )
    text = page_text(on)
    assert "Not applicable" not in text
    assert not re.search(r'id="vat_rate"[^>]*\sdisabled(?=[\s>])', text)
