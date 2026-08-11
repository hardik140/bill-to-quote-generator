"""Deterministic calculation engine. PRD FR-06 / TRD §7.

All math here is done with `Decimal`. This module has no I/O and no
framework dependencies, which keeps it trivially unit-testable and is the
part of the system that must never silently produce a wrong number.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.utils.money import to_money


@dataclass(frozen=True)
class LineResult:
    line_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


@dataclass(frozen=True)
class BillTotals:
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal


def compute_line(quantity: Decimal, rate: Decimal, gst_rate: Decimal) -> LineResult:
    """line_subtotal = quantity x unit_price; tax = line x gst_rate/100."""
    line_amount = to_money(quantity * rate)
    tax_amount = to_money(line_amount * gst_rate / Decimal("100"))
    total_amount = to_money(line_amount + tax_amount)
    return LineResult(line_amount=line_amount, tax_amount=tax_amount, total_amount=total_amount)


def compute_bill_totals(line_results: list[LineResult], other_adjustments: Decimal = Decimal("0.00")) -> BillTotals:
    """taxable_subtotal = sum(line_subtotal); grand_total = subtotal + tax + adjustments."""
    subtotal = to_money(sum((lr.line_amount for lr in line_results), Decimal("0.00")))
    tax_total = to_money(sum((lr.tax_amount for lr in line_results), Decimal("0.00")))
    grand_total = to_money(subtotal + tax_total + other_adjustments)
    return BillTotals(subtotal=subtotal, tax_total=tax_total, grand_total=grand_total)
