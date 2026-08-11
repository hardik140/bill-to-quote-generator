from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.ids import new_id

if TYPE_CHECKING:
    from app.models.document import Document

# processing_runs.status values
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)

    processor: Mapped[str] = mapped_column(String(50), nullable=False)
    processor_version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=RUN_RUNNING, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(String(1000))

    document: Mapped["Document"] = relationship(back_populates="processing_runs")
