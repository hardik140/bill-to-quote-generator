from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.scenario import Scenario


def add(db: Session, scenario: Scenario) -> Scenario:
    db.add(scenario)
    db.flush()
    return scenario


def get(db: Session, scenario_id: str) -> Scenario | None:
    stmt = select(Scenario).where(Scenario.id == scenario_id).options(selectinload(Scenario.items))
    return db.scalars(stmt).first()


def list_for_bill(db: Session, bill_id: str) -> list[Scenario]:
    stmt = (
        select(Scenario)
        .where(Scenario.bill_id == bill_id)
        .options(selectinload(Scenario.items))
        .order_by(Scenario.created_at)
    )
    return list(db.scalars(stmt))
