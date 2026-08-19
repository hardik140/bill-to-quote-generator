from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories import bill_repository, document_repository, generated_file_repository, scenario_repository
from app.schemas.document import (
    DocumentDetail,
    DocumentExtractResponse,
    DocumentFilesResponse,
    DocumentListResponse,
    DocumentSummary,
    DocumentUploadResponse,
)
from app.services.extraction_service import ExtractionError, extract_document
from app.services.storage_service import delete_document_storage, save_upload
from app.utils.file_validation import UploadValidationError

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
def upload_document(file: UploadFile, db: Session = Depends(get_db)) -> DocumentUploadResponse:
    try:
        stored = save_upload(file)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    document = document_repository.create(
        db,
        original_filename=file.filename,
        stored_filename=stored.stored_filename,
        mime_type=file.content_type,
        file_size=stored.file_size,
        file_hash=stored.file_hash,
    )
    db.commit()
    return DocumentUploadResponse(document_id=document.id, status=document.status)


@router.post("/{document_id}/extract", response_model=DocumentExtractResponse)
def extract(document_id: str, db: Session = Depends(get_db)) -> DocumentExtractResponse:
    document = document_repository.get(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if bill_repository.get_by_document(db, document_id) is not None:
        raise HTTPException(status_code=409, detail="Document has already been extracted.")

    try:
        bill = extract_document(db, document)
    except ExtractionError as exc:
        raise HTTPException(
            status_code=422,
            detail="Unable to confidently extract this document. Please review or enter the fields manually.",
        ) from exc

    return DocumentExtractResponse(document_id=document.id, status=document.status, bill_id=bill.id)


@router.get("", response_model=DocumentListResponse)
def list_documents(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)) -> DocumentListResponse:
    documents = document_repository.list_recent(db, limit=limit, offset=offset)
    summaries: list[DocumentSummary] = []
    for doc in documents:
        bill = bill_repository.get_by_document(db, doc.id)
        scenario_count = len(scenario_repository.list_for_bill(db, bill.id)) if bill else 0
        summaries.append(
            DocumentSummary(
                id=doc.id,
                original_filename=doc.original_filename,
                uploaded_at=doc.uploaded_at,
                status=doc.status,
                grand_total=bill.grand_total if bill else None,
                scenario_count=scenario_count,
            )
        )
    return DocumentListResponse(documents=summaries)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentDetail:
    document = document_repository.get(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    bill = bill_repository.get_by_document(db, document_id)
    return DocumentDetail(
        id=document.id,
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        file_size=document.file_size,
        uploaded_at=document.uploaded_at,
        status=document.status,
        bill_id=bill.id if bill else None,
        preview_url=f"/files/uploads/{document.stored_filename}",
    )


@router.get("/{document_id}/files", response_model=DocumentFilesResponse)
def list_files(document_id: str, db: Session = Depends(get_db)) -> DocumentFilesResponse:
    if document_repository.get(db, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    files = generated_file_repository.list_for_document(db, document_id)
    return DocumentFilesResponse(files=files)


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> None:
    document = document_repository.get(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    bill = bill_repository.get_by_document(db, document_id)
    bill_id = bill.id if bill else None
    stored_filename = document.stored_filename

    document_repository.delete(db, document)
    db.commit()

    delete_document_storage(stored_filename, document_id, bill_id)
