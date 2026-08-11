from decimal import Decimal

from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.scenario import (
    BASELINE_LABEL,
    SIMULATION_DISCLAIMER,
    TYPE_BASELINE,
    TYPE_SIMULATED,
)
from app.services.scenario_service import build_all_scenarios, build_scenario


def make_bill() -> Bill:
    bill = Bill(id="bill-1", document_id="doc-1", confirmed=True)
    bill.items = [
        BillItem(
            id="item-1",
            bill_id="bill-1",
            serial_no=1,
            description="A4 Paper Rim 75 GSM",
            gst_rate=Decimal("18.00"),
            quantity=Decimal("1"),
            unit="RIM",
            source_rate=Decimal("240.00"),
            taxable_rate=Decimal("240.00"),
            line_amount=Decimal("240.00"),
            tax_amount=Decimal("43.20"),
            total_amount=Decimal("283.20"),
            user_verified=True,
        ),
    ]
    return bill


def test_baseline_preserves_source_values_and_zero_markup():
    bill = make_bill()
    scenario = build_scenario(bill, TYPE_BASELINE, "Source / Baseline", Decimal("99"), "nearest_10")

    assert scenario.markup_percent == Decimal("0.00")
    assert scenario.rounding_mode == "none"
    assert scenario.disclaimer == BASELINE_LABEL
    assert scenario.items[0].adjusted_rate == Decimal("240.00")
    assert scenario.subtotal == Decimal("240.00")
    assert scenario.tax_total == Decimal("43.20")
    assert scenario.grand_total == Decimal("283.20")


def test_scenario_b_applies_markup():
    bill = make_bill()
    scenario = build_scenario(bill, TYPE_SIMULATED, "Scenario B", Decimal("10"), "none")

    assert scenario.disclaimer == SIMULATION_DISCLAIMER
    item = scenario.items[0]
    assert item.adjusted_rate == Decimal("264.00")  # 240 * 1.10
    assert item.line_amount == Decimal("264.00")
    assert item.tax_amount == Decimal("47.52")  # 264 * 18%
    assert scenario.grand_total == Decimal("311.52")


def test_scenario_c_applies_larger_markup_and_rounding():
    bill = make_bill()
    scenario = build_scenario(bill, TYPE_SIMULATED, "Scenario C", Decimal("20"), "nearest_10")

    item = scenario.items[0]
    assert item.adjusted_rate == Decimal("288.00")  # 240 * 1.20
    # raw grand total = 288 + 51.84 = 339.84 -> nearest 10 = 340.00
    assert scenario.grand_total == Decimal("340.00")


def test_scenario_snapshot_is_independent_of_source_item_mutation():
    bill = make_bill()
    scenario = build_scenario(bill, TYPE_SIMULATED, "Scenario B", Decimal("10"), "none")
    original_adjusted_rate = scenario.items[0].adjusted_rate

    # Mutate the source bill item after the scenario snapshot was built.
    bill.items[0].taxable_rate = Decimal("999.00")

    assert scenario.items[0].adjusted_rate == original_adjusted_rate
    assert scenario.items[0].source_item_id == "item-1"


def test_build_all_scenarios_returns_baseline_b_c_in_order():
    bill = make_bill()
    scenarios = build_all_scenarios(bill, Decimal("10"), Decimal("20"), "nearest_1")

    assert [s.scenario_type for s in scenarios] == [TYPE_BASELINE, TYPE_SIMULATED, TYPE_SIMULATED]
    assert scenarios[1].markup_percent == Decimal("10")
    assert scenarios[2].markup_percent == Decimal("20")


def test_negative_markup_rejected():
    import pytest

    from app.services.validation_service import ValidationError

    bill = make_bill()
    with pytest.raises(ValidationError):
        build_scenario(bill, TYPE_SIMULATED, "Scenario B", Decimal("-5"), "none")
