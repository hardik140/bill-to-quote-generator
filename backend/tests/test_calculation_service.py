from decimal import Decimal

from app.services.calculation_service import compute_bill_totals, compute_line


def test_compute_line_basic():
    result = compute_line(Decimal("1"), Decimal("240.00"), Decimal("18.00"))
    assert result.line_amount == Decimal("240.00")
    assert result.tax_amount == Decimal("43.20")
    assert result.total_amount == Decimal("283.20")


def test_compute_line_fractional_quantity():
    result = compute_line(Decimal("2.5"), Decimal("46.61"), Decimal("18.00"))
    assert result.line_amount == Decimal("116.53")  # 2.5 * 46.61 = 116.525 -> half-up
    assert result.tax_amount == to_money_helper(result.line_amount * Decimal("18") / Decimal("100"))


def to_money_helper(value: Decimal) -> Decimal:
    from app.utils.money import to_money

    return to_money(value)


def test_compute_line_zero_gst():
    result = compute_line(Decimal("3"), Decimal("10.00"), Decimal("0.00"))
    assert result.tax_amount == Decimal("0.00")
    assert result.total_amount == Decimal("30.00")


def test_compute_bill_totals_sums_lines():
    lines = [
        compute_line(Decimal("1"), Decimal("240.00"), Decimal("18.00")),
        compute_line(Decimal("2"), Decimal("55.00"), Decimal("12.00")),
    ]
    totals = compute_bill_totals(lines)
    assert totals.subtotal == Decimal("350.00")  # 240 + 110
    assert totals.tax_total == Decimal("56.40")  # 43.20 + 13.20
    assert totals.grand_total == Decimal("406.40")


def test_compute_bill_totals_empty_is_zero():
    totals = compute_bill_totals([])
    assert totals.subtotal == Decimal("0.00")
    assert totals.tax_total == Decimal("0.00")
    assert totals.grand_total == Decimal("0.00")


def test_compute_bill_totals_with_adjustment():
    lines = [compute_line(Decimal("1"), Decimal("100.00"), Decimal("0.00"))]
    totals = compute_bill_totals(lines, other_adjustments=Decimal("5.00"))
    assert totals.grand_total == Decimal("105.00")
