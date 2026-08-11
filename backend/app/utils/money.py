"""Decimal-only money helpers.

Per TRD §7 / PRD FR-06: all financial math uses `Decimal`, never binary
floating point. Every function here takes and returns `Decimal`.
"""

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def to_money(value: Decimal | str | int | float) -> Decimal:
    """Coerce a value to a 2-decimal-place Decimal using half-up rounding.

    `float` is accepted only for convenience at API boundaries (e.g. a JSON
    payload already parsed by Pydantic into float); it is immediately
    converted via `str()` to avoid binary floating-point artifacts.
    """
    if isinstance(value, float):
        value = str(value)
    d = value if isinstance(value, Decimal) else Decimal(value)
    return d.quantize(CENTS, rounding=ROUND_HALF_UP)


def round_to_nearest(value: Decimal, mode: str) -> Decimal:
    """Apply a scenario rounding policy (PRD FR-10) to a monetary value."""
    if mode == "none" or mode is None:
        return to_money(value)
    step = {"nearest_1": Decimal("1"), "nearest_5": Decimal("5"), "nearest_10": Decimal("10")}.get(mode)
    if step is None:
        raise ValueError(f"Unknown rounding mode: {mode}")
    quotient = (value / step).to_integral_value(rounding=ROUND_HALF_UP)
    return to_money(quotient * step)
