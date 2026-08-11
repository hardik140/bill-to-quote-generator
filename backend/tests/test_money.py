from decimal import Decimal

from app.utils.money import round_to_nearest, to_money


def test_to_money_quantizes_half_up():
    assert to_money(Decimal("10.005")) == Decimal("10.01")
    assert to_money(Decimal("10.004")) == Decimal("10.00")
    assert to_money("240") == Decimal("240.00")


def test_to_money_rejects_float_artifacts():
    # 0.1 + 0.2 == 0.30000000000000004 in binary float; to_money must not
    # propagate that artifact when a float slips in at an API boundary.
    assert to_money(0.1 + 0.2) == Decimal("0.30")


def test_round_to_nearest_none_is_passthrough():
    assert round_to_nearest(Decimal("123.45"), "none") == Decimal("123.45")


def test_round_to_nearest_1():
    assert round_to_nearest(Decimal("123.45"), "nearest_1") == Decimal("123.00")
    assert round_to_nearest(Decimal("123.55"), "nearest_1") == Decimal("124.00")


def test_round_to_nearest_5():
    assert round_to_nearest(Decimal("122.00"), "nearest_5") == Decimal("120.00")
    assert round_to_nearest(Decimal("123.00"), "nearest_5") == Decimal("125.00")


def test_round_to_nearest_10():
    assert round_to_nearest(Decimal("124.00"), "nearest_10") == Decimal("120.00")
    assert round_to_nearest(Decimal("125.00"), "nearest_10") == Decimal("130.00")


def test_round_to_nearest_unknown_mode_raises():
    import pytest

    with pytest.raises(ValueError):
        round_to_nearest(Decimal("1.00"), "bogus")
