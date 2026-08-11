"""Validation rules. TRD §10, PRD §11 (error message text is prescribed)."""

from decimal import Decimal, InvalidOperation


class ValidationError(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


def validate_quantity(quantity: Decimal | None) -> Decimal:
    if quantity is None:
        raise ValidationError("Quantity required", field="quantity")
    if quantity < 0:
        raise ValidationError("Quantity required", field="quantity")
    return quantity


def validate_rate(rate: Decimal | None) -> Decimal:
    if rate is None or rate < 0:
        raise ValidationError(
            "Rate must be a valid non-negative monetary value.", field="rate"
        )
    return rate


def validate_gst_rate(gst_rate: Decimal) -> Decimal:
    if gst_rate < 0 or gst_rate > 100:
        raise ValidationError("GST rate must be between 0 and 100.", field="gst_rate")
    return gst_rate


def validate_markup(markup: Decimal) -> Decimal:
    if markup < 0:
        raise ValidationError("Markup must be a non-negative percentage.", field="markup_percent")
    return markup


def parse_decimal(raw: str | Decimal | int | float, field: str) -> Decimal:
    try:
        value = raw if isinstance(raw, Decimal) else Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"{field} must be a valid number.", field=field) from exc
    return value


def check_total_reconciliation(
    extracted_total: Decimal | None, calculated_total: Decimal, tolerance: Decimal = Decimal("1.00")
) -> bool:
    """Returns True if extracted vs. calculated totals reconcile within tolerance.

    PRD §11: "Extracted total differs from calculated total. Please verify
    the source document." is shown by the caller (not raised) so the user
    can still proceed with manual review rather than being hard-blocked.
    """
    if extracted_total is None:
        return True
    return abs(extracted_total - calculated_total) <= tolerance
