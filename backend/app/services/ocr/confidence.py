"""Confidence-tier classification and the bounded OCR retry loop this
pipeline was missing entirely before this migration -- previously a
low-confidence page only set a `needs_review` flag after the fact; nothing
ever re-ran OCR. A low-confidence page now gets one heavier-preprocessed
re-run instead of silently keeping a bad first pass.

Deliberately independent of the DB/HTTP layer (no Session, no ORM model)
so the retry decision is unit-testable on its own.
"""

from pathlib import Path

import cv2

from app.core.config import settings
from app.services.ocr import preprocessing
from app.services.ocr.engine import OcrWord, run_ocr

HIGH_CONFIDENCE = 0.90
# settings.low_confidence_threshold (0.75) remains the medium/low boundary,
# unchanged from what the app already used for per-item review flagging.

MAX_ATTEMPTS = 2


def tier(confidence: float) -> str:
    if confidence >= HIGH_CONFIDENCE:
        return "high"
    if confidence >= settings.low_confidence_threshold:
        return "medium"
    return "low"


def _document_confidence(words: list[OcrWord]) -> float:
    scored = [w.confidence for w in words if w.confidence >= 0]
    if not scored:
        return 0.0
    return (sum(scored) / len(scored)) / 100.0


def run_page_with_retry(
    source_path: Path,
    mime_type: str,
    page_index: int,
    preprocessed_path: Path,
    image_out_dir: Path,
) -> tuple[list[OcrWord], int]:
    """Runs OCR on the already-preprocessed page; if page-level confidence
    lands in the low tier, re-renders the same page at a heavier
    preprocessing profile (denoise + sharpen on top of the existing
    pipeline, neither of which the pipeline had before this migration) and
    retries, up to MAX_ATTEMPTS total passes. Returns whichever attempt
    scored higher -- a retry is only kept if it actually did better, never
    swapped in blindly -- alongside how many attempts were made.
    """
    words = run_ocr(preprocessed_path)
    best_words, best_confidence = words, _document_confidence(words)
    attempts = 1

    while tier(best_confidence) == "low" and attempts < MAX_ATTEMPTS:
        attempts += 1
        raw_pages = (
            preprocessing.pdf_to_page_images(source_path)
            if mime_type == "application/pdf"
            else [preprocessing.load_image(source_path)]
        )
        if page_index >= len(raw_pages):
            break

        heavy = preprocessing.preprocess_page_heavy(raw_pages[page_index])
        heavy_path = image_out_dir / f"page_{page_index:03d}_retry{attempts}.png"
        cv2.imwrite(str(heavy_path), heavy)

        retry_words = run_ocr(heavy_path)
        retry_confidence = _document_confidence(retry_words)
        if retry_confidence > best_confidence:
            best_words, best_confidence = retry_words, retry_confidence

    return best_words, attempts
