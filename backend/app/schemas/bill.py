from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.config import settings


class BillItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    serial_no: int
    description: str
    hsn_sac: str | None = None
    gst_rate: Decimal
    quantity: Decimal
    unit: str | None = None
    source_rate: Decimal
    taxable_rate: Decimal
    line_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
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
    vendor_name: str | None = None
    vendor_address: str | None = None
    vendor_gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    buyer_name: str | None = None
    buyer_address: str | None = None
    currency: str
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    extraction_status: str
    confirmed: bool
    created_at: datetime
    updated_at: datetime
    items: list[BillItemOut] = []


class BillUpdate(BaseModel):
    vendor_name: str | None = None
    vendor_address: str | None = None
    vendor_gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    buyer_name: str | None = None
    buyer_address: str | None = None
    currency: str | None = None


class BillItemUpdate(BaseModel):
    description: str | None = None
    hsn_sac: str | None = None
    gst_rate: Decimal | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    source_rate: Decimal | None = None
    taxable_rate: Decimal | None = None


class BillItemCreate(BaseModel):
    description: str
    hsn_sac: str | None = None
    gst_rate: Decimal = Decimal("0")
    quantity: Decimal
    unit: str | None = None
    source_rate: Decimal
    taxable_rate: Decimal | None = None


class ItemReorderRequest(BaseModel):
    item_ids_in_order: list[str] = Field(..., min_length=1)


class ConfirmResponse(BaseModel):
    bill_id: str
    confirmed: bool
