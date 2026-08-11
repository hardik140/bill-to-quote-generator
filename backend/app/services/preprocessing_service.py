"""Document preprocessing. PRD FR-02: rotation/deskew, contrast, denoise,
resolution normalization, page-by-page handling for PDFs.
"""

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

MIN_WIDTH_PX = 1600  # resolution normalization floor for reliable OCR


def pdf_to_page_images(pdf_path: Path, dpi: int = 300) -> list[np.ndarray]:
    """Render each PDF page to a BGR numpy image via PyMuPDF (no poppler
    dependency needed for this path since PyMuPDF renders natively)."""
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


def _estimate_skew_angle(thresh: np.ndarray, search_range: float = 15.0) -> float:
    """Projection-profile skew estimate: the correct rotation maximizes the
    variance of per-row foreground pixel counts (text lines form sharp
    peaks when level). `minAreaRect` on the raw point cloud was tried first
    but is unreliable for sparse, mixed layouts (a title plus a few short
    header lines plus a table) -- verified empirically to report ~4 degrees
    of "skew" on a perfectly level, digitally-rendered page.
    """
    # Search on a downscaled copy purely for speed; the angle transfers.
    h, w = thresh.shape[:2]
    scale = min(1.0, 800.0 / max(h, w))
    small = cv2.resize(thresh, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_NEAREST) if scale < 1.0 else thresh

    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-search_range, search_range + 1.0, 1.0):
        score = _projection_variance(small, angle)
        if score > best_score:
            best_score, best_angle = score, angle
    for angle in np.arange(best_angle - 1.0, best_angle + 1.01, 0.1):
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
        return gray  # not worth rotating; avoids needless interpolation blur
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


def _remove_grid_lines(gray: np.ndarray) -> np.ndarray:
    """Erases ruled table borders before OCR.

    Tesseract's layout analysis routinely drops entire rows of a
    grid-bordered table (border pixels get classified as part of the text
    region and confuse connected-component analysis) -- verified empirically
    against a ruled invoice table where 2 of 3 item rows were silently lost
    without this step. Kernel lengths are sized relative to the image so
    long ruling lines are erased while normal glyph strokes (even bold
    headings) are left alone.
    """
    h, w = gray.shape[:2]
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    h_len = max(25, w // 30)
    v_len = max(25, h // 40)
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    lines = cv2.dilate(cv2.bitwise_or(horiz, vert), cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))

    cleaned_bw = cv2.subtract(bw, lines)
    return cv2.bitwise_not(cleaned_bw)


def preprocess_page(image_bgr: np.ndarray) -> np.ndarray:
    """Rotation correction, deskew, resolution normalization, contrast
    enhancement, noise reduction, and grid-line removal (FR-02), returns a
    binarized image ready for OCR.

    Grid-line removal runs before deskew/CLAHE/denoise: those steps
    resample every pixel (cubic interpolation, local contrast stretching),
    which turns crisp 1px ruling lines into slightly blurred bands that the
    line-removal morphology can no longer cleanly separate from adjacent
    glyphs -- verified empirically to silently drop entire table rows when
    ordered the other way round.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = _normalize_resolution(gray)
    gray = _remove_grid_lines(gray)
    gray = _deskew(gray)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # fastNlMeansDenoising gives marginally cleaner output but takes ~10s+
    # on a 300dpi page, blowing the <5s/page target (TRD §16); median blur
    # is near-instant and handles the salt-and-pepper noise typical of
    # phone-camera captures just as well for OCR purposes.
    gray = cv2.medianBlur(gray, 3)
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
