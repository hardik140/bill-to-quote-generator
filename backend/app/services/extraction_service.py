"""Extraction orchestration: preprocessing -> OCR -> parsing -> normalize
-> confidence -> persistence. TRD §5-6.

OCR never writes a "final" value directly -- every persisted BillItem is
created with user_verified=False so FR-05 human review is mandatory before
a bill can be confirmed.
"""

from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.bill import EXTRACTION_COMPLETED, EXTRACTION_NEEDS_REVIEW, Bill
from app.models.document import STATUS_FAILED, STATUS_PROCESSED, STATUS_PROCESSING, Document
from app.repositories import bill_repository, document_repository, processing_run_repository
from app.services import preprocessing_service
from app.services.calculation_service import compute_bill_totals, compute_line
from app.services.field_parser import HeaderFields, extract_document_total, parse_header_fields
from app.services.line_grouping import group_lines
from app.services.ocr_service import full_text, run_ocr
from app.services.table_parser import CandidateItem, parse_table
from app.services.validation_service import check_total_reconciliation

LOW_CONFIDENCE_ITEM_THRESHOLD = Decimal(str(settings.low_confidence_threshold))


class ExtractionError(Exception):
    pass


def _merge_header_fields(primary: HeaderFields, fallback: HeaderFields) -> HeaderFields:
    merged = HeaderFields(**vars(primary))
    for field_name, value in vars(fallback).items():
        if getattr(merged, field_name) is None and value is not None:
            setattr(merged, field_name, value)
    return merged


def extract_document(db: Session, document: Document) -> Bill:
    """Runs the full pipeline for an uploaded document and persists a Bill
    with candidate BillItems. Returns the created Bill (not yet confirmed).
    """
    run = processing_run_repository.start(
        db,
        document_id=document.id,
        processor=settings.ocr_processor_name,
        processor_version=settings.ocr_processor_version,
    )
    document_repository.set_status(db, document, STATUS_PROCESSING)
    db.commit()

    try:
        source_path = settings.uploads_dir / document.stored_filename
        image_out_dir = settings.images_dir / document.id
        page_paths = preprocessing_service.document_to_preprocessed_images(
            source_path, image_out_dir, document.mime_type
        )
        if not page_paths:
            raise ExtractionError("No pages could be rendered from the document.")

        header_fields = HeaderFields()
        all_candidate_items: list[CandidateItem] = []
        document_total: Decimal | None = None
        serial_offset = 0

        for page_path in page_paths:
            words = run_ocr(page_path)
            lines = group_lines(words)
            page_text = full_text(words)

            page_header = parse_header_fields(lines, page_text)
            header_fields = _merge_header_fields(header_fields, page_header)

            if document_total is None:
                document_total = extract_document_total(lines)

            page_items = parse_table(lines)
            for item in page_items:
                item.serial_no += serial_offset
            all_candidate_items.extend(page_items)
            serial_offset += len(page_items)

        bill = bill_repository.create(
            db,
            document_id=document.id,
            vendor_name=header_fields.vendor_name,
            vendor_address=header_fields.vendor_address,
            vendor_gstin=header_fields.vendor_gstin,
            invoice_number=header_fields.invoice_number,
            invoice_date=header_fields.invoice_date,
            buyer_name=header_fields.buyer_name,
            buyer_address=header_fields.buyer_address,
            currency=settings.default_currency,
        )

        needs_review = len(all_candidate_items) == 0
        line_results = []
        for candidate in all_candidate_items:
            quantity = candidate.quantity if candidate.quantity is not None else Decimal("0")
            taxable_rate = candidate.taxable_rate if candidate.taxable_rate is not None else Decimal("0")
            gst_rate = candidate.gst_rate if candidate.gst_rate is not None else Decimal("0")

            line_result = compute_line(quantity, taxable_rate, gst_rate)
            line_results.append(line_result)

            is_low_confidence = Decimal(str(candidate.confidence)) < LOW_CONFIDENCE_ITEM_THRESHOLD
            if candidate.ambiguous or is_low_confidence or candidate.quantity is None or candidate.taxable_rate is None:
                needs_review = True

            bill_repository.add_item(
                db,
                bill,
                serial_no=candidate.serial_no,
                description=candidate.description,
                hsn_sac=candidate.hsn_sac,
                gst_rate=gst_rate,
                quantity=quantity,
                unit=candidate.unit,
                source_rate=candidate.source_rate if candidate.source_rate is not None else Decimal("0"),
                taxable_rate=taxable_rate,
                line_amount=line_result.line_amount,
                tax_amount=line_result.tax_amount,
                total_amount=line_result.total_amount,
                confidence=Decimal(str(round(candidate.confidence, 4))),
                user_verified=False,
            )

        totals = compute_bill_totals(line_results)
        bill.subtotal = totals.subtotal
        bill.tax_total = totals.tax_total
        bill.grand_total = totals.grand_total

        if not check_total_reconciliation(document_total, totals.grand_total, tolerance=Decimal("2.00")):
            needs_review = True

        bill.extraction_status = EXTRACTION_NEEDS_REVIEW if needs_review else EXTRACTION_COMPLETED

        document_repository.set_status(db, document, STATUS_PROCESSED)
        processing_run_repository.complete(db, run)
        db.commit()
        db.refresh(bill)
        return bill

    except Exception as exc:  # noqa: BLE001 - surfaced to caller after cleanup
        db.rollback()
        document_repository.set_status(db, document, STATUS_FAILED)
        processing_run_repository.fail(db, run, str(exc))
        db.commit()
        raise ExtractionError(str(exc)) from exc
