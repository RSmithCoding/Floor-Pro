from decimal import Decimal

import pytest

from floorpro.domain.validation import (
    VAT_NUMBER_ERROR,
    VAT_RATE_ERROR,
    normalise_vat_number,
    validate_vat_rate,
)


def test_messages():
    assert VAT_RATE_ERROR == "Enter a VAT rate between 0 and 100, with up to two decimal places."
    assert VAT_NUMBER_ERROR == "Enter a UK VAT number, for example GB123456789."


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("20", Decimal("20.00")),
        ("17.5", Decimal("17.50")),
        (" 0 ", Decimal("0.00")),
        ("100", Decimal("100.00")),
        ("5.25", Decimal("5.25")),
    ],
)
def test_validate_vat_rate_accepts(raw, expected):
    assert validate_vat_rate(raw) == expected


@pytest.mark.parametrize("raw", ["-5", "150", "abc", "12.345", "", "NaN", "Infinity", "1e2"])
def test_validate_vat_rate_rejects(raw):
    with pytest.raises(ValueError, match="Enter a VAT rate between 0 and 100"):
        validate_vat_rate(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("gb 123 4567 89", "GB123456789"),
        ("GB123456789012", "GB123456789012"),
        ("GBGD001", "GBGD001"),
        ("gbha599", "GBHA599"),
    ],
)
def test_normalise_vat_number_accepts(raw, expected):
    assert normalise_vat_number(raw) == expected


@pytest.mark.parametrize("raw", ["GB12", "123456789", "FR123456789", "GBXX001"])
def test_normalise_vat_number_rejects(raw):
    with pytest.raises(ValueError, match="Enter a UK VAT number"):
        normalise_vat_number(raw)
