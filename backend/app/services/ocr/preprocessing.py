"""Document preprocessing. PRD FR-02: rotation/deskew, contrast, denoise,
resolution normalization, page-by-page handling for PDFs.
"""

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageOps

from app.services.ocr.engine import OcrWord

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
    pil_img = Image.open(path)
    pil_img = ImageOps.exif_transpose(pil_img)  # phone photos often carry an EXIF rotation tag
    pil_img = pil_img.convert("RGB")
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


def _order_quad_points(pts: np.ndarray) -> np.ndarray:
    """Sorts 4 arbitrary corner points into [top-left, top-right,
    bottom-right, bottom-left] via the standard sum/diff trick: top-left has
    the smallest x+y, bottom-right the largest x+y, top-right the smallest
    y-x, bottom-left the largest y-x.
    """
    pts = pts.reshape(4, 2).astype(np.float32)
    sums = pts.sum(axis=1)
    diffs = (pts[:, 1] - pts[:, 0])
    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = pts[np.argmin(sums)]
    ordered[2] = pts[np.argmax(sums)]
    ordered[1] = pts[np.argmin(diffs)]
    ordered[3] = pts[np.argmax(diffs)]
    return ordered


def _approx_quad(hull: np.ndarray) -> np.ndarray | None:
    """Reduces a convex hull to a 4-point polygon. Sweeps the
    `approxPolyDP` tolerance upward -- a physically imperfect page edge
    (curl, a folded/dog-eared corner) routinely breaks a *raw* contour's
    4-point approximation at a fixed tolerance, but its convex hull, given
    enough tolerance, still collapses cleanly to 4 points. Falls back to the
    hull's minimum-area bounding rectangle if no tolerance in the sweep
    yields exactly 4, so a page with real physical damage still gets a
    reasonable quad instead of no quad at all.
    """
    peri = cv2.arcLength(hull, True)
    for eps_frac in (0.02, 0.03, 0.05, 0.08, 0.1):
        approx = cv2.approxPolyDP(hull, eps_frac * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return approx.reshape(4, 2)
    rect = cv2.minAreaRect(hull)
    return cv2.boxPoints(rect)


def _find_document_quad(image_bgr: np.ndarray) -> np.ndarray | None:
    """Locates the 4-corner outline of a photographed document page via edge
    detection -- the classic "scanner app" approach. Returns ordered corner
    points in original-image coordinates, or None if no candidate
    confidently looks like a document page against its background (never
    guesses when uncertain: a wrong crop is worse than no crop).
    """
    h, w = image_bgr.shape[:2]
    work_width = 1000.0
    scale = work_width / w if w > work_width else 1.0
    small = (
        cv2.resize(image_bgr, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else image_bgr
    )

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    # Edge-preserving smoothing survives cluttered/textured backgrounds
    # (e.g. a keyboard) far better than a global blur + Otsu threshold.
    filtered = cv2.bilateralFilter(gray, 9, 75, 75)
    edges = cv2.Canny(filtered, 50, 150)
    edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    frame_area = small.shape[0] * small.shape[1]
    candidates = sorted(contours, key=cv2.contourArea, reverse=True)[:8]

    best_quad: np.ndarray | None = None
    best_area = 0.0
    for cnt in candidates:
        # The hull, not the raw contour, is what gets area-checked and
        # quad-approximated: a curled/folded edge undercounts the raw
        # contour's area and shatters its polygon approximation, but the
        # hull still represents "how much of the frame the page occupies."
        hull = cv2.convexHull(cnt)
        area = cv2.contourArea(hull)
        if not (0.15 * frame_area < area < 0.97 * frame_area):
            continue

        quad = _approx_quad(hull)
        if quad is None:
            continue

        ordered = _order_quad_points(quad)
        side_lengths = [float(np.linalg.norm(ordered[i] - ordered[(i + 1) % 4])) for i in range(4)]
        if min(side_lengths) < 0.2 * max(side_lengths):
            continue  # sliver / false positive, e.g. one edge of a keyboard

        if area > best_area:
            best_area = area
            best_quad = ordered

    if best_quad is None:
        return None

    return best_quad / scale


def _warp_quad(image_bgr: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Perspective-warps *image_bgr* so the given quadrilateral becomes a
    top-down axis-aligned rectangle, sized from the quad's own measured
    pixel dimensions (so output resolution reflects the photographed page,
    not an arbitrary fixed size).
    """
    tl, tr, br, bl = quad
    width = max(1, int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))))
    height = max(1, int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))))
    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    return cv2.warpPerspective(
        image_bgr,
        matrix,
        (width, height),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),  # white fill so stray corner gaps don't
    )                                  # inject a dark border into Otsu/CLAHE downstream


def _correct_perspective(image_bgr: np.ndarray) -> tuple[np.ndarray, bool]:
    """Detects and perspective-corrects the document page in a photographed
    image. Returns (image, corrected) -- when no confident document
    quadrilateral is found, returns the original image unchanged rather
    than guessing.
    """
    quad = _find_document_quad(image_bgr)
    if quad is None:
        return image_bgr, False
    warped = _warp_quad(image_bgr, quad)
    if warped.shape[0] < 50 or warped.shape[1] < 50:
        return image_bgr, False
    return warped, True


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
    """Preprocess document for OCR: perspective correction, illumination
    normalization, deskew, resolution normalization, contrast enhancement,
    and grid-line attenuation.
    """
    corrected_bgr, _ = _correct_perspective(image_bgr)
    gray = cv2.cvtColor(corrected_bgr, cv2.COLOR_BGR2GRAY)
    gray = _normalize_resolution(gray)
    gray = _normalize_illumination(gray)
    gray = _crop_border(gray)
    gray = _remove_grid_lines(gray)
    gray = _deskew(gray)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    return gray


def _denoise(gray: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)


def _sharpen(gray: np.ndarray) -> np.ndarray:
    """Unsharp mask: adds back (original - blurred), which amplifies edges
    without the harsher artefacts of a raw sharpening kernel.
    """
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=3)
    return cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)


def preprocess_page_heavy(image_bgr: np.ndarray) -> np.ndarray:
    """Heavier variant of preprocess_page() for a page whose first OCR pass
    came back low-confidence: adds denoising and sharpening on top of the
    standard pipeline. Neither existed anywhere in this module before --
    every prior page got the same fixed recipe regardless of how poor the
    source image actually was. Reserved for confidence-triggered retries
    (see ocr/confidence.py) rather than applied to every page, since both
    steps cost real time and can soften/distort an already-clean scan.
    """
    gray = preprocess_page(image_bgr)
    gray = _denoise(gray)
    gray = _sharpen(gray)
    return gray


def save_page_image(image: np.ndarray, out_dir: Path, page_index: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"page_{page_index:03d}.png"
    cv2.imwrite(str(out_path), image)
    return out_path


HEADER_CROP_FILENAME = "header_crop.png"
HEADER_CROP_FRACTION = 0.22  # top slice of the page that typically holds a letterhead


def generate_header_crop(source_path: Path, out_dir: Path, mime_type: str) -> Path | None:
    """Saves the top slice of page 1's *original, unprocessed* rendering as
    a plain image crop, for use as the Baseline PDF's letterhead visual.

    Called unconditionally, independent of whether extraction takes the
    digital-PDF fast path or the raster/OCR path -- this is a factual
    reproduction of whatever the uploaded document actually shows (colour,
    logo artwork, layout), never a generated or fabricated graphic, which
    is why it's only ever used on the Baseline PDF ("SOURCE / BASELINE —
    DERIVED FROM UPLOADED DOCUMENT"), never on Scenario B/C.
    """
    try:
        if mime_type == "application/pdf":
            pages = pdf_to_page_images(source_path)
        else:
            pages = [load_image(source_path)]
        if not pages:
            return None
        raw = pages[0]
        out_dir.mkdir(parents=True, exist_ok=True)
        h = raw.shape[0]
        crop = raw[: int(h * HEADER_CROP_FRACTION), :]
        out_path = out_dir / HEADER_CROP_FILENAME
        cv2.imwrite(str(out_path), crop)
        return out_path
    except Exception:
        return None  # letterhead image is a nice-to-have, never fatal to extraction


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
