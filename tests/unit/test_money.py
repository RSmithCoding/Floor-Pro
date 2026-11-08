from decimal import Decimal

import pytest

from floorpro.domain.money import (
    bp_to_percent,
    from_minor_units,
    percent_to_bp,
    round_money,
    to_minor_units,
)


def test_round_money_half_up():
    assert round_money(Decimal("1.005")) == Decimal("1.01")
    assert round_money(Decimal("1.004")) == Decimal("1.00")
    assert round_money(Decimal("-1.005")) == Decimal("-1.01")


def test_minor_units_round_trip():
    assert to_minor_units(Decimal("12.34")) == 1234
    assert from_minor_units(1234) == Decimal("12.34")
    assert to_minor_units(Decimal("0.005")) == 1


def test_percent_basis_points():
    assert percent_to_bp(Decimal("17.5")) == 1750
    assert percent_to_bp(Decimal("20")) == 2000
    assert bp_to_percent(2000) == Decimal("20.00")
    assert bp_to_percent(1750) == Decimal("17.50")


def test_percent_rejects_more_than_two_decimal_places():
    with pytest.raises(ValueError):
        percent_to_bp(Decimal("12.345"))


@pytest.mark.parametrize(
    "func, arg",
    [
        (round_money, 1.5),
        (to_minor_units, 1.5),
        (percent_to_bp, 17.5),
    ],
)
def test_floats_are_rejected(func, arg):
    with pytest.raises(TypeError):
        func(arg)


def test_int_inputs_for_minor_units_and_bp():
    with pytest.raises(TypeError):
        from_minor_units(12.0)
    with pytest.raises(TypeError):
        bp_to_percent(20.0)
