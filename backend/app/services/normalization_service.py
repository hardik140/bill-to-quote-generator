"""Normalization of raw OCR text into typed candidate values.
TRD §6 pipeline stage: OCR output -> candidate fields -> parser -> normalizer.
"""

import re
from decimal import Decimal, InvalidOperation

from app.services.ocr.postprocess import fix_numeric_ocr

NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
CURRENCY_STRIP_RE = re.compile(r"(?:rs\.?|inr|₹|\$|usd|eur|€|\/-|/-|\*)", re.IGNORECASE)

UNIT_SYNONYMS: dict[str, str] = {
    "PC": "PCS", "PCS": "PCS", "PIECE": "PCS", "PIECES": "PCS",
    "NO": "NOS", "NOS": "NOS", "NUMBER": "NOS", "NUMBERS": "NOS",
    "KG": "KG", "KGS": "KG", "KILOGRAM": "KG",
    "GM": "GM", "GMS": "GM", "GRAM": "GM", "GRAMS": "GM",
    "MTR": "MTR", "MTRS": "MTR", "METER": "MTR", "METRE": "MTR",
    "LTR": "LTR", "LTRS": "LTR", "LITRE": "LTR", "LITER": "LTR",
    "BOX": "BOX", "BOXES": "BOX",
    "SET": "SET", "SETS": "SET",
    "RIM": "RIM", "RIMS": "RIM",
    "DOZ": "DOZ", "DOZEN": "DOZ",
    "BAG": "BAG", "BAGS": "BAG",
    "PKT": "PKT", "PACKET": "PKT", "PACKETS": "PKT",
    "UNIT": "UNIT", "UNITS": "UNIT",
    "EA": "EA", "EACH": "EA",
}


def parse_decimal_loose(raw: str | None) -> Decimal | None:
    """Best-effort Decimal parse from noisy OCR text. Returns None rather
    than guessing when nothing number-like is found."""
    if not raw:
        return None
    cleaned = CURRENCY_STRIP_RE.sub("", raw).strip()
    cleaned = re.sub(r"(\d+)\s*\.\s*(\d{1,2})\b", r"\1.\2", cleaned)

    match = NUMBER_RE.search(cleaned)

    # A digit/letter confusion (e.g. "24O.OO" for "240.00") lets the search
    # above succeed on a truncated substring ("24") without ever reaching
    # the correction below, silently dropping the rest of the value. Always
    # attempt the fix and prefer it whenever it recovers *more* of the
    # candidate than the uncorrected parse did -- never when it recovers
    # less or the same, so an already-clean value is never second-guessed.
    cleaned_fix = fix_numeric_ocr(cleaned)
    if cleaned_fix != cleaned:
        fix_match = NUMBER_RE.search(cleaned_fix)
        if fix_match and (match is None or len(fix_match.group(0)) > len(match.group(0))):
            match = fix_match

    if not match:
        return None
    token = match.group(0).replace(",", "")
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def parse_int_loose(raw: str | None) -> int | None:
    value = parse_decimal_loose(raw)
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, OverflowError):
        return None


def normalize_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"[^A-Za-z]", "", raw).upper()
    if not cleaned:
        return None
    return UNIT_SYNONYMS.get(cleaned, cleaned[:20])
