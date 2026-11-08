from decimal import Decimal

import pytest

from floorpro.domain.currency import SUPPORTED_CURRENCIES, format_money, get_currency


def test_supported_currencies():
    assert [(c.code, c.symbol, c.name) for c in SUPPORTED_CURRENCIES.values()] == [
        ("GBP", "£", "Pound sterling"),
        ("EUR", "€", "Euro"),
        ("USD", "$", "US dollar"),
    ]


def test_get_currency_unknown():
    with pytest.raises(ValueError):
        get_currency("XYZ")


def test_format_money():
    assert format_money(Decimal("1234.5"), "GBP") == "£1,234.50"
    assert format_money(Decimal("-3"), "EUR") == "-€3.00"
    assert format_money(Decimal("0.005"), "USD") == "$0.01"
