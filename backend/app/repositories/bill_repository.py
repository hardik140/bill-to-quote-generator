from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.bill import Bill
from app.models.bill_item import BillItem


def create(db: Session, **fields) -> Bill:
    bill = Bill(**fields)
    db.add(bill)
    db.flush()
    return bill


def get(db: Session, bill_id: str) -> Bill | None:
    stmt = select(Bill).where(Bill.id == bill_id).options(selectinload(Bill.items))
    return db.scalars(stmt).first()


def get_by_document(db: Session, document_id: str) -> Bill | None:
    stmt = select(Bill).where(Bill.document_id == document_id).options(selectinload(Bill.items))
    return db.scalars(stmt).first()


def add_item(db: Session, bill: Bill, **fields) -> BillItem:
    item = BillItem(bill_id=bill.id, **fields)
    db.add(item)
    db.flush()
    return item


def get_item(db: Session, item_id: str) -> BillItem | None:
    return db.get(BillItem, item_id)


def delete_item(db: Session, item: BillItem) -> None:
    db.delete(item)
    db.flush()
