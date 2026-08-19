from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.ids import new_id

if TYPE_CHECKING:
    from app.models.bill_item import BillItem
    from app.models.scenario import Scenario


class ScenarioItem(Base):
    __tablename__ = "scenario_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bill_items.id", ondelete="CASCADE"), nullable=False
    )

    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    unit: Mapped[str | None] = mapped_column(String(20))

    baseline_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    markup_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"))
    adjusted_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    line_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    scenario: Mapped["Scenario"] = relationship(back_populates="items")
    source_item: Mapped["BillItem"] = relationship(back_populates="scenario_items")
