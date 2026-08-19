from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ScenarioConfigRequest(BaseModel):
    scenario_b_markup_percent: Decimal = Field(ge=0)
    scenario_c_markup_percent: Decimal = Field(ge=0)
    rounding: str = "none"


class ScenarioCreateResponse(BaseModel):
    scenario_ids: list[str]


class ScenarioItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_item_id: str
    description: str
    quantity: Decimal
    unit: str | None = None
    baseline_rate: Decimal
    markup_percent: Decimal
    adjusted_rate: Decimal
    line_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bill_id: str
    scenario_type: str
    label: str
    markup_percent: Decimal
    rounding_mode: str
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    disclaimer: str | None = None

    created_at: datetime
    items: list[ScenarioItemOut] = []


class ScenarioPdfResponse(BaseModel):
    scenario_id: str
    filename: str
    storage_path: str
    file_hash: str
