"""Document preprocessing. PRD FR-02: rotation/deskew, contrast, denoise,
resolution normalization, page-by-page handling for PDFs.
"""

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from app.services.ocr_service import OcrWord

MIN_WIDTH_PX = 2000


def extract_digital_pdf_words(pdf_path: Path) -> list[list[OcrWord]] | None:
    """Extract native digital words and bounding boxes directly from a vector PDF.
    Returns a list of word lists (one per page), or None if the PDF has little or
    no extractable text (e.g. scanned image).
    """
    doc = fitz.open(pdf_path)
    pages_words: list[list[OcrWord]] = []
    total_words = 0
    try:
        scale = 300.0 / 72.0
        for page in doc:
            words_data = page.get_text("words")
            page_words: list[OcrWord] = []
            for w in words_data:
                x0, y0, x1, y1, text, block_no, line_no, _ = w
                text_clean = text.strip()
                if not text_clean:
                    continue
                left = int(x0 * scale)
                top = int(y0 * scale)
                width = max(1, int((x1 - x0) * scale))
                height = max(1, int((y1 - y0) * scale))
                page_words.append(
                    OcrWord(
                        text=text_clean,
                        confidence=100.0,
                        left=left,
                        top=top,
                        width=width,
                        height=height,
                        line_num=int(line_no),
                        block_num=int(block_no),
                        par_num=1,
                    )
                )
            pages_words.append(page_words)
            total_words += len(page_words)
    finally:
        doc.close()

    if total_words < 8:
        return None
    return pages_words


def pdf_to_page_images(pdf_path: Path, dpi: int = 300) -> list[np.ndarray]:
    """Render each PDF page to a BGR numpy image via PyMuPDF."""
    images: list[np.ndarray] = []
    doc = fitz.open(pdf_path)
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            images.append(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
    finally:
        doc.close()
    return images


def load_image(path: Path) -> np.ndarray:
    pil_img = Image.open(path).convert("RGB")
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def _projection_variance(binary: np.ndarray, angle: float) -> float:
    h, w = binary.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(binary, matrix, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    row_sums = rotated.sum(axis=1).astype(np.float64)
    return float(row_sums.var())


def _estimate_skew_angle(thresh: np.ndarray, search_range: float = 14.0) -> float:
    h, w = thresh.shape[:2]
    scale = min(1.0, 400.0 / max(h, w))
    small = cv2.resize(thresh, (max(10, int(w * scale)), max(10, int(h * scale))), interpolation=cv2.INTER_NEAREST) if scale < 1.0 else thresh

    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-search_range, search_range + 1.0, 2.0):
        score = _projection_variance(small, angle)
        if score > best_score:
            best_score, best_angle = score, angle
    for angle in np.arange(best_angle - 1.5, best_angle + 1.6, 0.5):
        score = _projection_variance(small, angle)
        if score > best_score:
            best_score, best_angle = score, angle
    return best_angle


def _deskew(gray: np.ndarray) -> np.ndarray:
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    if cv2.countNonZero(thresh) < 20:
        return gray
    angle = _estimate_skew_angle(thresh)
    if abs(angle) < 0.3:
        return gray
    (h, w) = gray.shape[:2]
    center = (w // 2, h // 2)
    rot_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        gray, rot_matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def _normalize_resolution(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape[:2]
    if w >= MIN_WIDTH_PX:
        return gray
    scale = MIN_WIDTH_PX / w
    return cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)


def _crop_border(gray: np.ndarray, margin_frac: float = 0.005) -> np.ndarray:
    h, w = gray.shape[:2]
    m_h = max(1, int(h * margin_frac))
    m_w = max(1, int(w * margin_frac))
    return gray[m_h: h - m_h, m_w: w - m_w]


def _remove_grid_lines(gray: np.ndarray) -> np.ndarray:
    """Erases long ruled table borders before OCR without destroying character strokes or decimal points."""
    h, w = gray.shape[:2]

    bw = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
    )

    h_len = max(40, w // 20)
    v_len = max(40, h // 30)
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    lines = cv2.dilate(cv2.bitwise_or(horiz, vert), cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))

    cleaned_gray = gray.copy()
    cleaned_gray[lines > 0] = 255
    return cleaned_gray


def _crop_document_area(image_bgr: np.ndarray) -> np.ndarray:
    """Isolate the document if captured on an obvious background surface."""
    h, w = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (9, 9), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image_bgr

    img_area = h * w
    best_rect = None
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 0.50 * img_area < area < 0.98 * img_area:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw > 0.5 * w and ch > 0.5 * h:
                best_rect = (x, y, cw, ch)
                break

    if best_rect:
        x, y, cw, ch = best_rect
        pad_x = int(0.02 * cw)
        pad_y = int(0.02 * ch)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + cw + pad_x)
        y1 = min(h, y + ch + pad_y)
        return image_bgr[y0:y1, x0:x1]

    return image_bgr


def _normalize_illumination(gray: np.ndarray) -> np.ndarray:
    """Fast illumination normalization via downscaled morphology."""
    h, w = gray.shape[:2]
    small_w, small_h = max(10, w // 4), max(10, h // 4)
    small = cv2.resize(gray, (small_w, small_h))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    background = cv2.morphologyEx(small, cv2.MORPH_CLOSE, kernel)
    background_full = cv2.resize(background, (w, h))
    background_full = np.maximum(background_full, 1)
    normalized = np.uint8(np.clip((gray.astype(np.float32) / background_full.astype(np.float32)) * 255.0, 0, 255))
    return normalized


def preprocess_page(image_bgr: np.ndarray) -> np.ndarray:
    """Preprocess document for OCR: illumination normalization, deskew,
    resolution normalization, contrast enhancement, and grid-line attenuation.
    """
    cropped_bgr = _crop_document_area(image_bgr)
    gray = cv2.cvtColor(cropped_bgr, cv2.COLOR_BGR2GRAY)
    gray = _normalize_resolution(gray)
    gray = _normalize_illumination(gray)
    gray = _crop_border(gray)
    gray = _remove_grid_lines(gray)
    gray = _deskew(gray)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    return gray


def save_page_image(image: np.ndarray, out_dir: Path, page_index: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"page_{page_index:03d}.png"
    cv2.imwrite(str(out_path), image)
    return out_path


def document_to_preprocessed_images(source_path: Path, out_dir: Path, mime_type: str) -> list[Path]:
    if mime_type == "application/pdf":
        raw_pages = pdf_to_page_images(source_path)
    else:
        raw_pages = [load_image(source_path)]

    saved: list[Path] = []
    for idx, raw in enumerate(raw_pages):
        processed = preprocess_page(raw)
        saved.append(save_page_image(processed, out_dir, idx))
    return saved
