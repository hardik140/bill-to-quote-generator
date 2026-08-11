from datetime import datetime

from sqlalchemy.orm import Session

from app.models.processing_run import RUN_COMPLETED, RUN_FAILED, ProcessingRun


def start(db: Session, document_id: str, processor: str, processor_version: str) -> ProcessingRun:
    run = ProcessingRun(document_id=document_id, processor=processor, processor_version=processor_version)
    db.add(run)
    db.flush()
    return run


def complete(db: Session, run: ProcessingRun) -> None:
    run.status = RUN_COMPLETED
    run.completed_at = datetime.utcnow()
    db.flush()


def fail(db: Session, run: ProcessingRun, error_message: str) -> None:
    run.status = RUN_FAILED
    run.completed_at = datetime.utcnow()
    run.error_message = error_message[:1000]
    db.flush()
