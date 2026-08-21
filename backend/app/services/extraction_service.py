"""Extraction orchestration: preprocessing -> OCR -> parsing -> normalize
-> confidence -> persistence. TRD §5-6.

Scope (user decision, 2026-08-19): extract only each product's NAME and
RATE from the uploaded bill's line-item table -- quantities/GST are not
parsed; items are stored with quantity=1 and gst_rate=0 so a bill's total
is simply the sum of its product rates. Document-level vendor identity
(name/address/GSTIN/phone/email) and invoice reference/date *are* still
extracted (restored 2026-08-22) because the Baseline PDF's letterhead
needs them -- see field_parser.py. This is document-level metadata, not a
line item, so it doesn't reintroduce the per-item complexity that was
deliberately dropped.

OCR never writes a "final" value directly -- every persisted BillItem is
created with user_verified=False so FR-05 human review is mandatory before
a bill can be confirmed.
"""

import re
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
from app.services.ocr_postprocess import filter_noise_words
from app.services.ocr_service import full_text, run_ocr
from app.services.table_parser import CandidateItem, parse_table
from app.services.validation_service import check_total_reconciliation

LOW_CONFIDENCE_ITEM_THRESHOLD = Decimal(str(settings.low_confidence_threshold))

# Leading serial markers: "1." / "1)" / "1 -" always, and a bare "1 " only
# when it matches the row's serial number (see _clean_description).
_SERIAL_PUNCT_RE = re.compile(r"^\s*\d{1,3}\s*[.):\-]\s+")
_SERIAL_BARE_RE = re.compile(r"^\s*(\d{1,3})\s+")


class ExtractionError(Exception):
    pass


def _clean_description(description: str, serial_no: int = 0) -> str:
    """Strip leading OCR noise, grid lines, and serial prefixes attached to product names.

    Preserves valid product names starting with alphanumeric codes (e.g. "A4 Paper", "2 Inch Binder").
    """
    text = description.strip()
    if not text:
        return ""

    # Case A: Leading noise punctuation or border bars (e.g. "| ", "/ ", "- ", "— ", "' & ")
    text = re.sub(r"^[\|\/\-\:\;\.\,\'\"\`\~\[\]\(\)\{\}\&\#\s!—]+\s*", "", text)

    # Case B: Noise prefix + serial number with punctuation (e.g. "wi 2|", "i 1/", "a 3]", "ig 4/", "i me 14)", "ei 12)")
    text = re.sub(
        r"^[a-zA-Z]{1,3}(?:\s+[a-zA-Z]{1,3})?\s*\d{1,3}\s*[\|\/\]\)\:\.\-\\\'\`]+\s*",
        "",
        text,
    )

    # Case C: Punctuation-based serial numbers (e.g. "1.", "1)", "14)", "1 -", "1/")
    text = re.sub(r"^\d{1,3}\s*[.):\-\|\/\]\\]+\s*", "", text)

    # Case D: Single letter OCR line fragment followed by serial (e.g. "i 6 ", "i 8 ", "ie 11 ")
    if serial_no > 0:
        text = re.sub(rf"^[a-zA-Z]{{1,3}}\s+{serial_no}\s+", "", text)
        text = re.sub(rf"^{serial_no}\s+", "", text)

    # Clean leftover leading symbols
    text = re.sub(r"^[\|\/\-\:\;\.\,\'\"\`\~\[\]\(\)\{\}\&\#\s!—]+\s*", "", text)

    # Clean known OCR artifacts in common words
    text = re.sub(r"['`]?S\s*\/\-", "5/-", text)
    text = re.sub(r"\bFldid\s*Pen\b", "Fluid Pen", text, flags=re.IGNORECASE)

    return text.strip()


def _candidate_rate(candidate: CandidateItem) -> Decimal | None:
    """The single rate shown to the user: the printed price, preferring the
    tax-exclusive rate when the bill prints both."""
    return candidate.taxable_rate if candidate.taxable_rate is not None else candidate.source_rate


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

        # Baseline-PDF letterhead visual: a factual crop of the source
        # document's own header, independent of which extraction path
        # below actually runs (the digital fast-path never rasterizes).
        preprocessing_service.generate_header_crop(source_path, image_out_dir, document.mime_type)

        all_candidate_items: list[CandidateItem] = []
        document_total: Decimal | None = None
        header_fields = HeaderFields()
        serial_offset = 0

        # 1. Fast-path: try native vector PDF text extraction if digital PDF
        if document.mime_type == "application/pdf":
            digital_pages_words = preprocessing_service.extract_digital_pdf_words(source_path)
            if digital_pages_words:
                for page_index, page_words in enumerate(digital_pages_words):
                    words = filter_noise_words(page_words)
                    lines = group_lines(words)
                    if page_index == 0:
                        header_fields = parse_header_fields(lines, full_text(words))
                    if document_total is None:
                        document_total = extract_document_total(lines)
                    page_items = parse_table(lines)
                    for item in page_items:
                        item.serial_no += serial_offset
                    all_candidate_items.extend(page_items)
                    serial_offset += len(page_items)

        # 2. Fallback / Scanned / Image path: raster preprocessing + OCR
        if not all_candidate_items:
            page_paths = preprocessing_service.document_to_preprocessed_images(
                source_path, image_out_dir, document.mime_type
            )
            if not page_paths:
                raise ExtractionError("No pages could be rendered from the document.")

            serial_offset = 0
            for page_index, page_path in enumerate(page_paths):
                words = run_ocr(page_path)
                words = filter_noise_words(words)
                lines = group_lines(words)

                if page_index == 0:
                    header_fields = parse_header_fields(lines, full_text(words))

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
            currency=settings.default_currency,
            vendor_name=header_fields.vendor_name,
            vendor_address=header_fields.vendor_address,
            vendor_gstin=header_fields.vendor_gstin,
            vendor_phone=header_fields.vendor_phone,
            vendor_email=header_fields.vendor_email,
            invoice_number=header_fields.invoice_number,
            invoice_date=header_fields.invoice_date,
        )

        needs_review = len(all_candidate_items) == 0
        line_results = []
        for candidate in all_candidate_items:
            rate = _candidate_rate(candidate)
            quantity = Decimal("1")
            gst_rate = Decimal("0")

            line_result = compute_line(quantity, rate if rate is not None else Decimal("0"), gst_rate)
            line_results.append(line_result)

            is_low_confidence = Decimal(str(candidate.confidence)) < LOW_CONFIDENCE_ITEM_THRESHOLD
            if candidate.ambiguous or is_low_confidence or rate is None:
                needs_review = True

            bill_repository.add_item(
                db,
                bill,
                serial_no=candidate.serial_no,
                description=_clean_description(candidate.description, candidate.serial_no),
                gst_rate=gst_rate,
                quantity=quantity,
                source_rate=candidate.source_rate if candidate.source_rate is not None else (rate if rate is not None else Decimal("0")),
                taxable_rate=candidate.taxable_rate if candidate.taxable_rate is not None else (rate if rate is not None else Decimal("0")),
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
