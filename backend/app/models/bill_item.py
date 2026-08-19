from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.ids import new_id

if TYPE_CHECKING:
    from app.models.bill import Bill
    from app.models.scenario_item import ScenarioItem


class BillItem(Base):
    __tablename__ = "bill_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False, index=True
    )

    serial_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    unit: Mapped[str | None] = mapped_column(String(20))

    # See DATA.md §7 - source_rate is what appeared on the document (may be
    # tax-inclusive); taxable_rate is the rate used as the calculation basis.
    # They are kept distinct so nothing is silently assumed.
    source_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    taxable_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    line_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    bill: Mapped["Bill"] = relationship(back_populates="items")
    scenario_items: Mapped[list["ScenarioItem"]] = relationship(
        back_populates="source_item", cascade="all, delete-orphan", passive_deletes=True
    )
