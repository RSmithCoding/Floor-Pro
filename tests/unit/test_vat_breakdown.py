"""data-model.md "Customer type rules" (FR-025 to FR-027)."""

import pytest

from floorpro.domain.customers import resolve_vat_breakdown


@pytest.mark.parametrize(
    "old_type, new_type, requested, expected",
    [
        (None, "domestic", None, False),  # new domestic: off by default
        (None, "domestic", True, True),  # new domestic: can opt in
        (None, "trade", False, True),  # new trade: forced on
        (None, "trade", None, True),
        ("domestic", "trade", False, True),  # domestic -> trade: forced on, locked
        ("trade", "domestic", None, True),  # trade -> domestic: stays on
        ("trade", "domestic", False, False),  # ...until explicitly unticked
        ("domestic", "domestic", True, True),  # domestic toggles: saved as chosen
        ("domestic", "domestic", False, False),
        ("trade", "trade", False, True),  # trade can never turn it off
    ],
)
def test_customer_type_rules(old_type, new_type, requested, expected):
    assert resolve_vat_breakdown(old_type, new_type, requested) is expected


def test_domestic_keeps_previous_value_when_not_asked():
    assert resolve_vat_breakdown("domestic", "domestic", None, previous=True) is True
    assert resolve_vat_breakdown("domestic", "domestic", None, previous=False) is False
