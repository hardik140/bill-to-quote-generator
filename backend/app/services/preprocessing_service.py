"""Document preprocessing. PRD FR-02: rotation/deskew, contrast, denoise,
resolution normalization, page-by-page handling for PDFs.
"""

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

MIN_WIDTH_PX = 2000  # raised from 1600 — extra pixels give Tesseract cleaner glyphs


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
    of \"skew\" on a perfectly level, digitally-rendered page.
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


def _crop_border(gray: np.ndarray, margin_frac: float = 0.005) -> np.ndarray:
    """Crop a thin border margin to eliminate page-edge artifacts (scanner
    shadows, camera vignetting) that confuse Tesseract layout analysis."""
    h, w = gray.shape[:2]
    m_h = max(1, int(h * margin_frac))
    m_w = max(1, int(w * margin_frac))
    return gray[m_h: h - m_h, m_w: w - m_w]


def _remove_grid_lines(gray: np.ndarray) -> np.ndarray:
    """Erases ruled table borders before OCR.

    Tesseract's layout analysis routinely drops entire rows of a
    grid-bordered table (border pixels get classified as part of the text
    region and confuse connected-component analysis) -- verified empirically
    against a ruled invoice table where 2 of 3 item rows were silently lost
    without this step.

    Kernel lengths are sized relative to the image so long ruling lines are
    erased while normal glyph strokes (even bold headings) are left alone.
    Kernel sizes are larger than the original to reliably catch thick borders
    typical of Indian invoice forms printed/scanned at 300 dpi.
    """
    h, w = gray.shape[:2]

    # Try Otsu first; fall back to adaptive threshold for unevenly lit images
    # (phone-camera captures often have non-uniform backgrounds that confuse
    # global Otsu, producing very few foreground pixels and missing borders).
    _, bw_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if cv2.countNonZero(bw_otsu) < (h * w * 0.01):
        # Fewer than 1% foreground pixels — Otsu probably failed; use adaptive
        bw = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10
        )
    else:
        bw = bw_otsu

    # Larger kernels (was w//30, h//40) to catch thick double-rule borders
    h_len = max(40, w // 20)
    v_len = max(40, h // 30)
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    lines = cv2.dilate(cv2.bitwise_or(horiz, vert), cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))

    cleaned_bw = cv2.subtract(bw, lines)
    return cv2.bitwise_not(cleaned_bw)


def _crop_document_area(image_bgr: np.ndarray) -> np.ndarray:
    """Isolate the main white paper document if photographed on a dark desk/surface."""
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
        if 0.25 * img_area < area < 0.98 * img_area:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw > 0.3 * w and ch > 0.3 * h:
                best_rect = (x, y, cw, ch)
                break

    if best_rect:
        x, y, cw, ch = best_rect
        pad_x = int(0.01 * cw)
        pad_y = int(0.01 * ch)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + cw + pad_x)
        y1 = min(h, y + ch + pad_y)
        return image_bgr[y0:y1, x0:x1]

    return image_bgr


def _normalize_illumination(gray: np.ndarray) -> np.ndarray:
    """Normalize non-uniform lighting / shadows from mobile camera captures."""
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (31, 31))
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    # Avoid zero division
    background = np.maximum(background, 1)
    normalized = np.uint8(np.clip((gray.astype(np.float32) / background.astype(np.float32)) * 255.0, 0, 255))
    return normalized


def preprocess_page(image_bgr: np.ndarray) -> np.ndarray:
    """Rotation correction, deskew, resolution normalization, contrast
    enhancement, noise reduction, border crop, and grid-line removal (FR-02).
    Returns a binarized image ready for OCR.
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
