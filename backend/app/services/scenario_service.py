"""Scenario generation engine. PRD FR-07/08/09/10, TRD §8, DATA.md §8-9.

Scenario items are copied from the confirmed baseline at generation time,
creating an immutable snapshot (DATA.md §9) — later edits to the source
bill must never silently change an already-generated scenario.
"""

from decimal import Decimal

from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.scenario import (
    BASELINE_LABEL,
    SIMULATION_DISCLAIMER,
    TYPE_BASELINE,
    TYPE_SIMULATED,
    Scenario,
)
from app.models.scenario_item import ScenarioItem
from app.services.validation_service import validate_markup
from app.utils.money import round_to_nearest, to_money

ZERO = Decimal("0.00")


def _build_scenario_item(item: BillItem, markup_percent: Decimal) -> ScenarioItem:
    baseline_rate = item.taxable_rate
    adjusted_rate = to_money(baseline_rate * (1 + markup_percent / Decimal("100")))
    line_amount = to_money(item.quantity * adjusted_rate)
    tax_amount = to_money(line_amount * item.gst_rate / Decimal("100"))
    total_amount = to_money(line_amount + tax_amount)

    return ScenarioItem(
        source_item_id=item.id,
        description=item.description,
        quantity=item.quantity,
        unit=item.unit,
        baseline_rate=baseline_rate,
        markup_percent=markup_percent,
        adjusted_rate=adjusted_rate,
        line_amount=line_amount,
        tax_amount=tax_amount,
        total_amount=total_amount,
    )


def build_scenario(
    bill: Bill,
    scenario_type: str,
    label: str,
    markup_percent: Decimal,
    rounding_mode: str,
) -> Scenario:
    """Build (but do not persist) a Scenario with its ScenarioItem snapshot.

    Baseline (FR-07) preserves confirmed source values exactly: markup is
    forced to 0 and no rounding is applied, regardless of caller input.
    Simulated scenarios (B/C) apply the requested markup and, per FR-10,
    the configured rounding is applied to the scenario's grand_total.
    """
    is_baseline = scenario_type == TYPE_BASELINE
    effective_markup = ZERO if is_baseline else validate_markup(markup_percent)
    effective_rounding = "none" if is_baseline else rounding_mode

    scenario_items = [_build_scenario_item(item, effective_markup) for item in bill.items]

    subtotal = to_money(sum((si.line_amount for si in scenario_items), ZERO))
    tax_total = to_money(sum((si.tax_amount for si in scenario_items), ZERO))
    raw_grand_total = to_money(subtotal + tax_total)
    grand_total = round_to_nearest(raw_grand_total, effective_rounding)

    scenario = Scenario(
        bill_id=bill.id,
        scenario_type=scenario_type,
        label=label,
        markup_percent=effective_markup,
        rounding_mode=effective_rounding,
        subtotal=subtotal,
        tax_total=tax_total,
        grand_total=grand_total,
        disclaimer=BASELINE_LABEL if is_baseline else SIMULATION_DISCLAIMER,
    )
    scenario.items = scenario_items
    return scenario


def build_all_scenarios(
    bill: Bill,
    scenario_b_markup_percent: Decimal,
    scenario_c_markup_percent: Decimal,
    rounding_mode: str,
) -> list[Scenario]:
    return [
        build_scenario(bill, TYPE_BASELINE, "Source / Baseline", ZERO, "none"),
        build_scenario(
            bill,
            TYPE_SIMULATED,
            "Scenario B — Internal Estimate",
            scenario_b_markup_percent,
            rounding_mode,
        ),
        build_scenario(
            bill,
            TYPE_SIMULATED,
            "Scenario C — Internal Estimate",
            scenario_c_markup_percent,
            rounding_mode,
        ),
    ]
