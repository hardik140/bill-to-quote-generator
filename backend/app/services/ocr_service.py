"""OCR wrapper around pytesseract/Tesseract. TRD §6: OCR produces
candidate words with bounding boxes and confidence, never final financial
values directly.
"""

from dataclasses import dataclass
from pathlib import Path

import pytesseract
from pytesseract import Output

from app.core.config import settings

try:
    pytesseract.pytesseract.tesseract_cmd = settings.resolved_tesseract_cmd()
except Exception:
    pass


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float  # 0-100, Tesseract native scale (-1 for whitespace-only)
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


def run_ocr(image_path: Path, lang: str | None = None, config: str | None = None) -> list[OcrWord]:
    """Run Tesseract OCR on *image_path* and return a flat list of OcrWord
    objects, one per recognised token.

    ``config`` overrides the default Tesseract config string from settings.
    Use ``--psm 4`` (single column of text blocks) for structured invoice
    layouts — empirically shown to dramatically improve confidence scores
    over the default auto-PSM on bordered Indian invoices.
    """
    data = pytesseract.image_to_data(
        str(image_path),
        lang=lang or settings.ocr_language,
        config=config if config is not None else settings.tesseract_config,
        output_type=Output.DICT,
    )
    words: list[OcrWord] = []
    n = len(data["text"])
    for i in range(n):
        text = data["text"][i].strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1.0
        words.append(
            OcrWord(
                text=text,
                confidence=conf,
                left=int(data["left"][i]),
                top=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
                line_num=int(data["line_num"][i]),
                block_num=int(data["block_num"][i]),
                par_num=int(data["par_num"][i]),
            )
        )
    return words


def full_text(words: list[OcrWord]) -> str:
    lines: dict[tuple[int, int, int], list[OcrWord]] = {}
    for w in words:
        lines.setdefault(w.line_key, []).append(w)
    ordered_keys = sorted(lines.keys())
    return "\n".join(" ".join(w.text for w in sorted(lines[k], key=lambda w: w.left)) for k in ordered_keys)
