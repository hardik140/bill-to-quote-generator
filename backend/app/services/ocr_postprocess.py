"""OCR post-processing: filter noise words and correct common OCR confusions
before feeding words into line_grouping / field_parser / table_parser.

TRD §6: OCR output is a candidate — this stage removes obvious artefacts
without fabricating values. All decisions here are conservative: when in
doubt, the word is kept (better to have noise than to silently discard data).
"""

import re

from app.services.ocr_service import OcrWord

# Characters that, when they make up the *entire* word, are pure OCR artefacts
# from ruled table borders: vertical bar, backslash, braces, tilde, brackets.
_PURE_NOISE_RE = re.compile(r"^[|\\/{}\[\]~`_*#]+$")

# Minimum confidence to retain a word (Tesseract native 0-100 scale).
_MIN_CONFIDENCE = 20.0

# OCR digit/letter confusions in purely numeric contexts.
_DIGIT_FIXES = str.maketrans("OoIlSsZzBq", "0011552289")


def filter_noise_words(words: list[OcrWord]) -> list[OcrWord]:
    """Remove words that are clearly OCR artefacts from table borders or
    low-quality regions.
    """
    result: list[OcrWord] = []
    for w in words:
        if _PURE_NOISE_RE.match(w.text):
            continue
        if w.confidence >= 0 and w.confidence < _MIN_CONFIDENCE:
            if not re.search(r"[A-Za-z0-9]", w.text):
                continue
        result.append(w)
    return result


def fix_numeric_ocr(raw: str) -> str:
    """Best-effort correction of common OCR digit/letter confusions in a
    string that is *expected* to be numeric (e.g. a rate or quantity cell).
    """
    stripped = raw.strip()
    if not stripped:
        return raw

    # Strip currency / suffix artefacts
    cleaned = re.sub(r"(?:rs\.?|inr|₹|\$|usd|eur|€|\/-|/-|\*)", "", stripped, flags=re.IGNORECASE).strip()
    # Normalize spaced decimals like "240 . 00" -> "240.00"
    cleaned = re.sub(r"(\d+)\s*[\.]\s*(\d{1,2})\b", r"\1.\2", cleaned)

    alphanum = [c for c in cleaned if c.isalnum()]
    if not alphanum:
        return cleaned

    digit_count = sum(1 for c in alphanum if c.isdigit())
    if digit_count / len(alphanum) < 0.35:
        return cleaned

    return cleaned.translate(_DIGIT_FIXES)
