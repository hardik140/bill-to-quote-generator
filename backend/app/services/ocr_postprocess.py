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
_PURE_NOISE_RE = re.compile(r"^[|\\/{}\[\]~`]+$")

# Minimum confidence to retain a word (Tesseract native 0-100 scale).
# Words below this threshold AND matching noise patterns are dropped.
# Set conservatively: 25 keeps genuine but blurry text; pure-noise words
# above this threshold are still dropped by _PURE_NOISE_RE.
_MIN_CONFIDENCE = 25.0

# OCR digit/letter confusions in purely numeric contexts.
# Applied only when the surrounding characters are already numeric so we
# don't blindly convert letters in description text.
_DIGIT_FIXES = str.maketrans("OoIlSsZzBq", "0011550028")


def filter_noise_words(words: list[OcrWord]) -> list[OcrWord]:
    """Remove words that are clearly OCR artefacts from table borders or
    low-quality regions.

    Rules applied (in order):
    1. Drop words whose *entire* text is one or more pure-border characters
       (``|``, ``\\``, ``{``, ``}``, ``~``, ``[``, ``]``, ``/``).
    2. Drop words with confidence below ``_MIN_CONFIDENCE`` that contain no
       alphanumeric characters at all (these are always noise).
    """
    result: list[OcrWord] = []
    for w in words:
        # Rule 1: pure noise token regardless of confidence
        if _PURE_NOISE_RE.match(w.text):
            continue
        # Rule 2: low-confidence, zero alphanumeric content
        if w.confidence >= 0 and w.confidence < _MIN_CONFIDENCE:
            if not re.search(r"[A-Za-z0-9]", w.text):
                continue
        result.append(w)
    return result


def fix_numeric_ocr(raw: str) -> str:
    """Best-effort correction of common OCR digit/letter confusions in a
    string that is *expected* to be numeric (e.g. a rate or quantity cell).

    Only called from field_parser / normalization paths on tokens already
    identified as candidate numbers — never applied to free-form description
    text to avoid corrupting product names.

    Examples:
        "S0O0"  -> "5000"
        "l8%"   -> "18%"
        "42.3l" -> "42.31"
    """
    # Only apply fixes if the string looks mostly numeric
    # (digits + punctuation > 50% of chars after stripping spaces)
    stripped = raw.strip()
    alphanum = [c for c in stripped if c.isalnum()]
    if not alphanum:
        return raw
    digit_count = sum(1 for c in alphanum if c.isdigit())
    if digit_count / len(alphanum) < 0.4:
        # More letters than digits — likely a description word, skip
        return raw
    return stripped.translate(_DIGIT_FIXES)
