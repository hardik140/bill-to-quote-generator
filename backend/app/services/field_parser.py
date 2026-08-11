"""Header field extraction (FR-03). Regex/heuristic candidates only —
TRD §6: OCR output is a candidate, never a confirmed value. Every field
produced here is surfaced for human review before it can be confirmed.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.line_grouping import OcrLine
from app.services.normalization_service import parse_decimal_loose

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]Z[A-Z\d]\b")
INVOICE_NO_RE = re.compile(
    r"(?:invoice|bill|inv)\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Z0-9/\-]{3,})", re.IGNORECASE
)
DATE_RE = re.compile(r"\b([0-3]?\d)[/\-.]([0-1]?\d)[/\-.](\d{2,4})\b")
DATE_LABEL_RE = re.compile(r"\bdate\b", re.IGNORECASE)
BUYER_LABEL_RE = re.compile(r"\b(bill\s*to|ship\s*to|buyer|m/s)\b[:\-]?", re.IGNORECASE)
BOILERPLATE_RE = re.compile(
    r"^(tax\s+invoice|invoice|bill|estimate|quotation|original|duplicate)$", re.IGNORECASE
)
NON_ADDRESS_HINT_RE = re.compile(
    r"(invoice|gstin|date|bill\s*to|ship\s*to|buyer|phone|mobile|email|www\.)", re.IGNORECASE
)


@dataclass
class HeaderFields:
    vendor_name: str | None = None
    vendor_address: str | None = None
    vendor_gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    buyer_name: str | None = None
    buyer_address: str | None = None


def _parse_date(match: re.Match) -> date | None:
    d, m, y = match.groups()
    y = int(y)
    if y < 100:
        y += 2000
    try:
        return date(y, int(m), int(d))
    except ValueError:
        try:
            return date(y, int(d), int(m))  # tolerate mm/dd if dd/mm is invalid
        except ValueError:
            return None


def extract_gstin(text: str) -> str | None:
    match = GSTIN_RE.search(text.upper())
    return match.group(0) if match else None


def extract_invoice_number(text: str) -> str | None:
    match = INVOICE_NO_RE.search(text)
    return match.group(1).strip(" :-") if match else None


def extract_invoice_date(lines: list[OcrLine]) -> date | None:
    for line in lines:
        if DATE_LABEL_RE.search(line.text):
            match = DATE_RE.search(line.text)
            if match:
                parsed = _parse_date(match)
                if parsed:
                    return parsed
    for line in lines:
        match = DATE_RE.search(line.text)
        if match:
            parsed = _parse_date(match)
            if parsed:
                return parsed
    return None


def extract_vendor_name(lines: list[OcrLine]) -> str | None:
    for line in lines[:8]:
        text = line.text.strip()
        if len(text) < 3:
            continue
        if BOILERPLATE_RE.match(text):
            continue
        if GSTIN_RE.search(text.upper()) or DATE_RE.search(text):
            continue
        return text
    return None


def extract_vendor_address(lines: list[OcrLine], vendor_name: str | None) -> str | None:
    if not vendor_name:
        return None
    start = None
    for i, line in enumerate(lines[:10]):
        if line.text.strip() == vendor_name:
            start = i + 1
            break
    if start is None:
        return None
    parts = []
    for line in lines[start : start + 3]:
        text = line.text.strip()
        if not text or NON_ADDRESS_HINT_RE.search(text) or GSTIN_RE.search(text.upper()):
            break
        parts.append(text)
    return ", ".join(parts) if parts else None


def extract_buyer_name_and_address(lines: list[OcrLine]) -> tuple[str | None, str | None]:
    for i, line in enumerate(lines):
        match = BUYER_LABEL_RE.search(line.text)
        if not match:
            continue
        remainder = line.text[match.end() :].strip(" :-")
        name = remainder or None
        addr_start = i + 1 if not remainder else i + 1
        if not name and i + 1 < len(lines):
            name = lines[i + 1].text.strip()
            addr_start = i + 2
        parts = []
        for l2 in lines[addr_start : addr_start + 2]:
            text = l2.text.strip()
            if not text or NON_ADDRESS_HINT_RE.search(text):
                break
            parts.append(text)
        return name, (", ".join(parts) if parts else None)
    return None, None


GRAND_TOTAL_RE = re.compile(r"grand\s*total|net\s*amount|total\s*amount\s*payable", re.IGNORECASE)


def extract_document_total(lines: list[OcrLine]) -> Decimal | None:
    """Best-effort extraction of the invoice's own printed grand total, used
    only to flag a possible calculation mismatch (PRD §11) -- never used as
    a source of truth for stored financial values."""
    for line in reversed(lines):
        if GRAND_TOTAL_RE.search(line.text):
            value = parse_decimal_loose(line.text)
            if value is not None:
                return value
    return None


def parse_header_fields(lines: list[OcrLine], full_text: str) -> HeaderFields:
    vendor_name = extract_vendor_name(lines)
    buyer_name, buyer_address = extract_buyer_name_and_address(lines)
    return HeaderFields(
        vendor_name=vendor_name,
        vendor_address=extract_vendor_address(lines, vendor_name),
        vendor_gstin=extract_gstin(full_text),
        invoice_number=extract_invoice_number(full_text),
        invoice_date=extract_invoice_date(lines),
        buyer_name=buyer_name,
        buyer_address=buyer_address,
    )
