from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class DocumentUploadResponse(BaseModel):
    document_id: str
    status: str


class DocumentExtractResponse(BaseModel):
    document_id: str
    status: str
    bill_id: str


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    uploaded_at: datetime
    status: str
    grand_total: Decimal | None = None
    scenario_count: int = 0


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]


class DocumentDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    mime_type: str
    file_size: int
    uploaded_at: datetime
    status: str
    bill_id: str | None = None
    preview_url: str


class GeneratedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scenario_id: str
    file_type: str
    filename: str
    storage_path: str
    generated_at: datetime


class DocumentFilesResponse(BaseModel):
    files: list[GeneratedFileOut]
