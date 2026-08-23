import numpy as np
import cv2

from app.services.ocr import preprocessing as pp

# A page-like quadrilateral against a noisy/textured background, standing in
# for a photographed document (e.g. paper on a busy desk). Slightly rotated
# and skewed so corner ordering and perspective warping are both exercised.
_TRUE_QUAD = np.array(
    [
        [120, 80],  # top-left
        [700, 50],  # top-right
        [740, 560],  # bottom-right
        [90, 540],  # bottom-left
    ],
    dtype=np.int32,
)


def _textured_background(seed: int, h: int = 600, w: int = 800) -> np.ndarray:
    rng = np.random.default_rng(seed)
    bg = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    return cv2.GaussianBlur(bg, (3, 3), 0)


def _synthetic_document_photo() -> np.ndarray:
    img = _textured_background(seed=42)
    cv2.fillConvexPoly(img, _TRUE_QUAD, (250, 250, 250))
    return img


def test_order_quad_points_sorts_arbitrary_order_into_tl_tr_br_bl():
    # Deliberately shuffled input order.
    shuffled = np.array([[740, 560], [90, 540], [120, 80], [700, 50]], dtype=np.float32)
    ordered = pp._order_quad_points(shuffled)

    tl, tr, br, bl = ordered
    assert tl[0] < tr[0] and tl[1] < bl[1]
    assert tr[0] > tl[0] and tr[1] < br[1]
    assert br[0] > bl[0] and br[1] > tr[1]
    assert bl[0] < br[0] and bl[1] > tl[1]


def test_find_document_quad_detects_page_against_cluttered_background():
    img = _synthetic_document_photo()
    detected = pp._find_document_quad(img)

    assert detected is not None
    expected = pp._order_quad_points(_TRUE_QUAD.astype(np.float32))
    per_corner_distance = np.linalg.norm(detected - expected, axis=1)
    assert (per_corner_distance < 15.0).all(), per_corner_distance


def test_find_document_quad_returns_none_when_no_document_present():
    img = _textured_background(seed=7)
    assert pp._find_document_quad(img) is None


def test_correct_perspective_warps_when_quad_found():
    img = _synthetic_document_photo()
    corrected, was_corrected = pp._correct_perspective(img)

    assert was_corrected is True
    # The warped output is a top-down rectangle roughly the page's own
    # measured pixel size, not the full noisy background frame.
    assert corrected.shape != img.shape


def test_correct_perspective_falls_back_unchanged_when_uncertain():
    img = _textured_background(seed=7)
    corrected, was_corrected = pp._correct_perspective(img)

    assert was_corrected is False
    assert corrected is img


def test_warp_quad_produces_rectangle_sized_from_measured_corners():
    img = _synthetic_document_photo()
    ordered = pp._order_quad_points(_TRUE_QUAD.astype(np.float32))
    warped = pp._warp_quad(img, ordered)

    tl, tr, br, bl = ordered
    expected_width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    expected_height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))

    assert warped.shape[1] == int(expected_width)
    assert warped.shape[0] == int(expected_height)


def test_preprocess_page_completes_without_raising_on_cluttered_photo():
    img = _synthetic_document_photo()
    out = pp.preprocess_page(img)

    assert out.ndim == 2  # grayscale output
    assert out.shape[0] > 0 and out.shape[1] > 0
