from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field

from app.core.config import settings


class BillItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    serial_no: int
    description: str
    rate: Decimal = Field(validation_alias=AliasChoices("rate", "taxable_rate", "source_rate"))
    confidence: Decimal | None = None
    user_verified: bool

    @computed_field
    @property
    def low_confidence(self) -> bool:
        if self.confidence is None:
            return True
        return float(self.confidence) < settings.low_confidence_threshold


class BillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    currency: str
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    extraction_status: str
    confirmed: bool
    created_at: datetime
    updated_at: datetime
    items: list[BillItemOut] = []


class BillItemUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    description: str | None = None
    rate: Decimal | None = Field(default=None, validation_alias=AliasChoices("rate", "taxable_rate", "source_rate"))


class BillItemCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    description: str
    rate: Decimal = Field(validation_alias=AliasChoices("rate", "taxable_rate", "source_rate"))


class ItemReorderRequest(BaseModel):
    item_ids_in_order: list[str] = Field(..., min_length=1)


class ConfirmResponse(BaseModel):
    bill_id: str
    confirmed: bool
