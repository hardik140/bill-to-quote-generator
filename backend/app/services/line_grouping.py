"""Groups raw OCR words into lines and gap-clustered cells, the shared
building block for both header-field parsing and table-column parsing.
"""

from dataclasses import dataclass

from app.services.ocr_service import OcrWord

CELL_GAP_FACTOR = 1.8  # gap > this * avg char width => new cell


@dataclass
class OcrCell:
    words: list[OcrWord]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def left(self) -> int:
        return min(w.left for w in self.words)

    @property
    def right(self) -> int:
        return max(w.right for w in self.words)

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def confidence(self) -> float:
        confs = [w.confidence for w in self.words if w.confidence >= 0]
        return sum(confs) / len(confs) if confs else 0.0


@dataclass
class OcrLine:
    words: list[OcrWord]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def top(self) -> int:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> int:
        return max(w.bottom for w in self.words)

    def cells(self) -> list[OcrCell]:
        return group_cells(self.words)


def group_lines(words: list[OcrWord]) -> list[OcrLine]:
    """Clusters words into visual rows by vertical position alone.

    Tesseract's own block/paragraph/line segmentation (`line_key`) is
    unreliable on grid-bordered tables -- ruled borders routinely get
    mis-read as column/block boundaries, scrambling row order. Clustering
    directly on y-coordinates is robust to that and is what actually
    reflects "which words sit on the same printed line".
    """
    if not words:
        return []

    heights = sorted(w.height for w in words if w.height > 0)
    median_height = heights[len(heights) // 2] if heights else 20
    tolerance = max(4.0, median_height * 0.6)

    ordered = sorted(words, key=lambda w: (w.top + w.bottom) / 2)
    clusters: list[list[OcrWord]] = []
    cluster_sums: list[float] = []
    cluster_counts: list[int] = []

    for w in ordered:
        center_y = (w.top + w.bottom) / 2
        match_idx = None
        for i in range(len(clusters)):
            mean_y = cluster_sums[i] / cluster_counts[i]
            if abs(center_y - mean_y) <= tolerance:
                match_idx = i
                break
        if match_idx is None:
            clusters.append([w])
            cluster_sums.append(center_y)
            cluster_counts.append(1)
        else:
            clusters[match_idx].append(w)
            cluster_sums[match_idx] += center_y
            cluster_counts[match_idx] += 1

    lines = [OcrLine(words=sorted(ws, key=lambda w: w.left)) for ws in clusters]
    lines.sort(key=lambda ln: ln.top)
    return lines


def group_cells(words: list[OcrWord]) -> list[OcrCell]:
    if not words:
        return []
    ordered = sorted(words, key=lambda w: w.left)
    avg_char_width = max(
        1.0, sum(w.width / max(len(w.text), 1) for w in ordered) / len(ordered)
    )
    # Empirically, in-phrase word gaps run ~0.7-0.8x avg char width while
    # real column gaps run 3x+ -- CELL_GAP_FACTOR sits well clear of both.
    gap_threshold = avg_char_width * CELL_GAP_FACTOR

    cells: list[OcrCell] = []
    current: list[OcrWord] = [ordered[0]]
    for prev, cur in zip(ordered, ordered[1:]):
        gap = cur.left - prev.right
        if gap > gap_threshold:
            cells.append(OcrCell(words=current))
            current = [cur]
        else:
            current.append(cur)
    cells.append(OcrCell(words=current))
    return cells
