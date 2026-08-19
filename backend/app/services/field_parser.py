"""Field parsing helpers.

The app extracts only two things from an uploaded bill: each product's
name and its rate (user decision, 2026-08-19) -- everything else
(vendor/buyer/invoice metadata, GST, quantities) is deliberately ignored.
The single helper kept here pulls the bill's own printed grand total,
which is used only to flag a possible extraction mismatch (PRD §11),
never as a source of truth for stored financial values.
"""

import re
from decimal import Decimal

from app.services.line_grouping import OcrLine
from app.services.normalization_service import parse_decimal_loose

GRAND_TOTAL_RE = re.compile(r"grand\s*total|net\s*amount|total\s*amount\s*payable|^total\b", re.IGNORECASE)


def extract_document_total(lines: list[OcrLine]) -> Decimal | None:
    for line in reversed(lines):
        if GRAND_TOTAL_RE.search(line.text):
            value = parse_decimal_loose(line.text)
            if value is not None:
                return value
    return None
