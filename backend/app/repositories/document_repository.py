from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


def create(db: Session, **fields) -> Document:
    doc = Document(**fields)
    db.add(doc)
    db.flush()
    return doc


def get(db: Session, document_id: str) -> Document | None:
    return db.get(Document, document_id)


def list_recent(db: Session, limit: int = 50, offset: int = 0) -> list[Document]:
    stmt = select(Document).order_by(Document.uploaded_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def set_status(db: Session, document: Document, status: str) -> None:
    document.status = status
    db.flush()


def delete(db: Session, document: Document) -> None:
    db.delete(document)
    db.flush()
