"""Header field extraction (vendor identity + invoice reference) plus the
bill's own printed grand total.

TRD §6: OCR output is a candidate, never a confirmed value -- every field
here is a best-effort regex/heuristic guess. The pipeline currently
extracts only product name + rate per line item (user decision,
2026-08-19); this module covers the *document-level* fields needed for a
Baseline-PDF letterhead (vendor name/address/GSTIN/phone/email, Ref No.,
date). It must never be used to render Scenario B/C, which stay unbranded
per the PRD's anti-impersonation rule.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.line_grouping import OcrLine
from app.services.normalization_service import parse_decimal_loose

GRAND_TOTAL_RE = re.compile(r"grand\s*total|net\s*amount|total\s*amount\s*payable|^total\b", re.IGNORECASE)

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]Z[A-Z\d]\b")
INVOICE_NO_RE = re.compile(
    r"(?:invoice|bill|ref)\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Z0-9/\-]{2,})", re.IGNORECASE
)
DATE_RE = re.compile(r"\b([0-3]?\d)[/\-.]([0-1]?\d)[/\-.](\d{2,4})\b")
DATE_LABEL_RE = re.compile(r"\bdate\b", re.IGNORECASE)
BOILERPLATE_RE = re.compile(
    r"^(tax\s+invoice|invoice|bill|estimate|quotation|original|duplicate)$", re.IGNORECASE
)
NON_ADDRESS_HINT_RE = re.compile(
    r"(invoice|gstin|ref\.?\s*no|date|bill\s*to|ship\s*to|buyer|www\.)", re.IGNORECASE
)

# Indian mobile numbers: optional +91/0 prefix, 10 digits, often preceded by
# "(M)", "Mob", "Phone", "Ph", "Cell", "Contact" -- but a bare 10-digit run
# next to those labels is matched too since many bills omit the label.
PHONE_RE = re.compile(
    r"(?:\(m\)|mob(?:ile)?|ph(?:one)?|cell|contact|call)?\s*[:.\-]?\s*"
    r"(\+?91[\s\-]?)?([6-9]\d{9})",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


@dataclass
class HeaderFields:
    vendor_name: str | None = None
    vendor_address: str | None = None
    vendor_gstin: str | None = None
    vendor_phone: str | None = None
    vendor_email: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None


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


def extract_document_total(lines: list[OcrLine]) -> Decimal | None:
    for line in reversed(lines):
        if GRAND_TOTAL_RE.search(line.text):
            value = parse_decimal_loose(line.text)
            if value is not None:
                return value
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


def extract_phone(text: str) -> str | None:
    match = PHONE_RE.search(text)
    if not match:
        return None
    return match.group(2)


def extract_email(text: str) -> str | None:
    match = EMAIL_RE.search(text)
    return match.group(0) if match else None


def extract_vendor_name(lines: list[OcrLine]) -> str | None:
    """Heuristic: the vendor's printed business name is almost always the
    largest/topmost non-boilerplate line on the first page (a letterhead)."""
    for line in lines[:8]:
        text = line.text.strip()
        if len(text) < 3:
            continue
        if BOILERPLATE_RE.match(text):
            continue
        if GSTIN_RE.search(text.upper()) or DATE_RE.search(text) or EMAIL_RE.search(text):
            continue
        if PHONE_RE.search(text) and len(text) < 20:
            continue  # a lone phone-number line, not a business name
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
        if EMAIL_RE.search(text) or (PHONE_RE.search(text) and len(text) < 20):
            break
        parts.append(text)
    return ", ".join(parts) if parts else None


def parse_header_fields(lines: list[OcrLine], full_text: str) -> HeaderFields:
    vendor_name = extract_vendor_name(lines)
    return HeaderFields(
        vendor_name=vendor_name,
        vendor_address=extract_vendor_address(lines, vendor_name),
        vendor_gstin=extract_gstin(full_text),
        vendor_phone=extract_phone(full_text),
        vendor_email=extract_email(full_text),
        invoice_number=extract_invoice_number(full_text),
        invoice_date=extract_invoice_date(lines),
    )
