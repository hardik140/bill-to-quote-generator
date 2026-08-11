from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generated_file import GeneratedFile


def create(db: Session, **fields) -> GeneratedFile:
    record = GeneratedFile(**fields)
    db.add(record)
    db.flush()
    return record


def list_for_document(db: Session, document_id: str) -> list[GeneratedFile]:
    from app.models.bill import Bill
    from app.models.scenario import Scenario

    stmt = (
        select(GeneratedFile)
        .join(Scenario, GeneratedFile.scenario_id == Scenario.id)
        .join(Bill, Scenario.bill_id == Bill.id)
        .where(Bill.document_id == document_id)
        .order_by(GeneratedFile.generated_at)
    )
    return list(db.scalars(stmt))
