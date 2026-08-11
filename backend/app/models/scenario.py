from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.ids import new_id

if TYPE_CHECKING:
    from app.models.bill import Bill
    from app.models.generated_file import GeneratedFile
    from app.models.scenario_item import ScenarioItem

# scenarios.scenario_type values
TYPE_BASELINE = "BASELINE"
TYPE_SIMULATED = "SIMULATED"

# Convenience labels for the three MVP scenarios (DATA.md §8)
SCENARIO_BASELINE = "BASELINE"
SCENARIO_B = "SCENARIO_B"
SCENARIO_C = "SCENARIO_C"

SIMULATION_DISCLAIMER = "SIMULATED / INTERNAL ESTIMATE — NOT A VENDOR QUOTATION"
BASELINE_LABEL = "SOURCE / BASELINE — DERIVED FROM UPLOADED DOCUMENT"

ROUNDING_NONE = "none"
ROUNDING_NEAREST_1 = "nearest_1"
ROUNDING_NEAREST_5 = "nearest_5"
ROUNDING_NEAREST_10 = "nearest_10"


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bills.id"), nullable=False, index=True
    )

    scenario_type: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    markup_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"))
    rounding_mode: Mapped[str] = mapped_column(String(20), default=ROUNDING_NONE)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    disclaimer: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    bill: Mapped["Bill"] = relationship(back_populates="scenarios")
    items: Mapped[list["ScenarioItem"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
    generated_files: Mapped[list["GeneratedFile"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
