from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.ids import new_id

if TYPE_CHECKING:
    from app.models.bill_item import BillItem
    from app.models.document import Document
    from app.models.scenario import Scenario

# bills.extraction_status values
EXTRACTION_PENDING = "pending"
EXTRACTION_COMPLETED = "completed"
EXTRACTION_NEEDS_REVIEW = "needs_review"
EXTRACTION_FAILED = "failed"


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=False, unique=True
    )

    vendor_name: Mapped[str | None] = mapped_column(String(255))
    vendor_address: Mapped[str | None] = mapped_column(String(500))
    vendor_gstin: Mapped[str | None] = mapped_column(String(20))
    invoice_number: Mapped[str | None] = mapped_column(String(100), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    buyer_name: Mapped[str | None] = mapped_column(String(255))
    buyer_address: Mapped[str | None] = mapped_column(String(500))
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    extraction_status: Mapped[str] = mapped_column(
        String(20), default=EXTRACTION_PENDING, nullable=False
    )
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="bill")
    items: Mapped[list["BillItem"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="BillItem.serial_no"
    )
    scenarios: Mapped[list["Scenario"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
    )
