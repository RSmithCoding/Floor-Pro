import pytest

from floorpro.domain.validation import (
    normalise_postcode,
    phone_digits,
    postcode_compact,
    validate_email,
    validate_phone,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("sw1a1aa", ("SW1A 1AA", False)),
        (" bs1 4dj ", ("BS1 4DJ", False)),
        ("gir0aa", ("GIR 0AA", False)),
        ("M1 1AE", ("M1 1AE", False)),
        ("ec1a  1bb", ("EC1A 1BB", False)),
        ("hello", ("HELLO", True)),
        ("12345", ("12345", True)),
    ],
)
def test_normalise_postcode(raw, expected):
    assert normalise_postcode(raw) == expected


def test_postcode_compact():
    assert postcode_compact("BS1 4DJ") == "BS14DJ"
    assert postcode_compact(" bs1 4dj ") == "BS14DJ"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("07700 900123", "07700900123"),
        ("+44 7700 900123", "07700900123"),
        ("+44 (0)7700 900123", "07700900123"),
        ("(01234) 567-890", "01234567890"),
        ("0044 117 496 0000", "01174960000"),
    ],
)
def test_phone_digits(raw, expected):
    assert phone_digits(raw) == expected


def test_validate_phone():
    assert validate_phone("12345") == "Enter a phone number with at least 7 digits."
    assert validate_phone("07700 900123") is None
    assert validate_phone("+44 7700 900123") is None


def test_validate_email():
    assert validate_email("jane@example") is not None
    assert validate_email("not an email") is not None
    assert validate_email("Jane.Smith@Example.com") is None
