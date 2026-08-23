"""OCR engine wrapper around PaddleOCR. TRD §6: OCR produces candidate
words with bounding boxes and confidence, never final financial values
directly.

PaddleOCR's base pipeline detects text at *line* granularity by default --
one box per visually-clustered run of text, not one per word. Every
downstream column/cell clustering in this app (line_grouping.group_cells,
and everything table_parser.py builds on it) depends on word-level boxes,
the same way Tesseract's image_to_data provided them. Passing
return_word_box=True splits each recognised line into per-word boxes too,
which is what makes this a genuine drop-in for the existing OcrWord
contract instead of silently breaking table-column detection.

Verified 2026-08-23 against the installed paddleocr==3.7.0 by running a
real inference call and inspecting the result object -- the schema below
(text_word / text_word_boxes / rec_scores) is not guessed from docs, which
are empty on this package; docs also don't mention it, but on this
Windows/CPU machine, running with the default oneDNN backend crashes with
NotImplementedError in onednn_instruction.cc on the very first predict()
call. Disabling MKLDNN (see Settings.ocr_enable_mkldnn) works around it at
a real speed cost (~70s/page here vs. a crash). Confirm whether Render's
Linux container needs the same workaround before assuming it does.
"""

from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.core.config import settings


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float  # 0-100 scale
    left: int
    top: int
    width: int
    height: int
    line_num: int
    block_num: int
    par_num: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def line_key(self) -> tuple[int, int, int]:
        return (self.block_num, self.par_num, self.line_num)


_engine = None
_engine_lock = Lock()


def _get_engine():
    """Lazy process-wide singleton -- PaddleOCR's model weights must only
    be loaded once (init alone took ~40s cold / ~5s warm-cached in
    verification), never per-request.
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from paddleocr import PaddleOCR

                _engine = PaddleOCR(
                    lang=settings.ocr_language,
                    enable_mkldnn=settings.ocr_enable_mkldnn,
                )
    return _engine


def run_ocr(image_path: Path) -> list[OcrWord]:
    """Run PaddleOCR on *image_path* and return a flat list of OcrWord
    objects, one per recognised word -- the same contract run_ocr() has
    always had, so line_grouping.py, table_parser.py, field_parser.py, and
    extraction_service.py need no changes to consume it.
    """
    result = _get_engine().predict(
        str(image_path),
        return_word_box=True,
        use_doc_orientation_classify=True,
        use_doc_unwarping=True,
    )
    if not result:
        return []
    page = result[0]

    text_word = page["text_word"] or []
    text_word_boxes = page["text_word_boxes"] or []
    rec_scores = page["rec_scores"] or []

    words: list[OcrWord] = []
    for line_idx, (line_words, line_boxes) in enumerate(zip(text_word, text_word_boxes)):
        # PaddleOCR scores recognition per detected line, not per word --
        # every word inherits its line's score rather than a fabricated
        # per-word figure. table_parser._row_confidence already averages
        # word confidences per cell, so cells built from one line collapse
        # to that line's own score, which is the correct behaviour.
        line_confidence = float(rec_scores[line_idx]) * 100.0 if line_idx < len(rec_scores) else -1.0
        for word_text, box in zip(line_words, line_boxes):
            text = word_text.strip()
            if not text:
                continue
            x1, y1, x2, y2 = (int(v) for v in box)
            words.append(
                OcrWord(
                    text=text,
                    confidence=line_confidence,
                    left=x1,
                    top=y1,
                    width=max(1, x2 - x1),
                    height=max(1, y2 - y1),
                    line_num=line_idx,
                    block_num=0,
                    par_num=1,
                )
            )
    return words


def full_text(words: list[OcrWord]) -> str:
    lines: dict[tuple[int, int, int], list[OcrWord]] = {}
    for w in words:
        lines.setdefault(w.line_key, []).append(w)
    ordered_keys = sorted(lines.keys())
    return "\n".join(" ".join(w.text for w in sorted(lines[k], key=lambda w: w.left)) for k in ordered_keys)
