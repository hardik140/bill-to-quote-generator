"""Line-item table extraction (FR-04). Column order is never assumed —
the header row is located and its column x-positions drive assignment of
every data row, per PRD FR-04 ("must not assume every bill has the same
column order").
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.services.line_grouping import OcrCell, OcrLine
from app.services.normalization_service import (
    normalize_unit,
    parse_decimal_loose,
    parse_int_loose,
)

COL_SERIAL = "serial"
COL_DESCRIPTION = "description"
COL_HSN = "hsn"
COL_GST = "gst"
COL_QTY = "qty"
COL_UNIT = "unit"
COL_RATE = "rate"  # taxable / tax-exclusive rate
COL_RATE_INCL = "rate_incl"  # tax-inclusive rate as printed
COL_AMOUNT = "amount"

NUMERIC_COLS = {COL_GST, COL_QTY, COL_RATE, COL_RATE_INCL, COL_AMOUNT}

STOP_LINE_RE = re.compile(
    r"(grand\s*total|sub\s*total|^total\b|total\s*amount|amount\s*in\s*words|"
    r"terms\s*(&|and)\s*conditions|declaration|authoris|bank\s*details)",
    re.IGNORECASE,
)

MIN_HEADER_MATCHES = 3


def _normalize_phrase(text: str) -> str:
    return re.sub(r"[^a-z0-9%]", "", text.lower())


def classify_header_cell(text: str) -> str | None:
    norm = _normalize_phrase(text)
    if not norm:
        return None
    if "hsn" in norm or "sac" in norm:
        return COL_HSN
    if norm in ("no", "sr", "srno", "sl", "slno", "sno") or "serial" in norm or norm == "#":
        return COL_SERIAL
    if "desc" in norm or "particular" in norm or "item" in norm or "goods" in norm or "product" in norm:
        return COL_DESCRIPTION
    if "qty" in norm or "quantity" in norm or "qnty" in norm:
        return COL_QTY
    if "uom" in norm or norm == "per" or norm == "unit":
        return COL_UNIT
    if "gst" in norm or "cgst" in norm or "sgst" in norm or "igst" in norm or "taxrate" in norm:
        return COL_GST
    if "taxable" in norm and ("value" in norm or "amount" in norm):
        return COL_AMOUNT
    if "amount" in norm or "total" in norm or "value" in norm:
        return COL_AMOUNT
    if "rate" in norm or "price" in norm:
        return COL_RATE_INCL if "incl" in norm else COL_RATE
    return None


@dataclass
class TableHeader:
    line_index: int
    columns: dict[str, float]  # column_type -> center_x


def find_header(lines: list[OcrLine]) -> TableHeader | None:
    best: TableHeader | None = None
    best_score = 0
    for idx, line in enumerate(lines):
        columns: dict[str, float] = {}
        for cell in line.cells():
            col_type = classify_header_cell(cell.text)
            if col_type and col_type not in columns:
                columns[col_type] = cell.center_x
        score = len(columns)
        has_core = COL_DESCRIPTION in columns and (COL_QTY in columns or COL_RATE in columns or COL_RATE_INCL in columns)
        if score >= MIN_HEADER_MATCHES and has_core and score > best_score:
            best = TableHeader(line_index=idx, columns=columns)
            best_score = score
    return best


def _assign_cells_to_columns(cells: list[OcrCell], columns: dict[str, float]) -> dict[str, list[OcrCell]]:
    assigned: dict[str, list[OcrCell]] = {}
    for cell in cells:
        nearest = min(columns.items(), key=lambda kv: abs(kv[1] - cell.center_x))[0]
        assigned.setdefault(nearest, []).append(cell)
    return assigned


@dataclass
class CandidateItem:
    serial_no: int
    description: str
    hsn_sac: str | None
    gst_rate: Decimal | None
    quantity: Decimal | None
    unit: str | None
    source_rate: Decimal | None
    taxable_rate: Decimal | None
    extracted_amount: Decimal | None
    confidence: float  # 0-1
    ambiguous: bool = field(default=False)


def _row_confidence(cells: list[OcrCell]) -> float:
    confs = [c.confidence for c in cells if c.words]
    if not confs:
        return 0.0
    return max(0.0, min(1.0, (sum(confs) / len(confs)) / 100.0))


def parse_table(lines: list[OcrLine]) -> list[CandidateItem]:
    header = find_header(lines)
    if header is None:
        return []

    items: list[CandidateItem] = []
    auto_serial = 0
    for line in lines[header.line_index + 1 :]:
        if STOP_LINE_RE.search(line.text):
            break
        cells = line.cells()
        if not cells:
            continue

        assigned = _assign_cells_to_columns(cells, header.columns)
        description = " ".join(c.text for c in assigned.get(COL_DESCRIPTION, []))
        numeric_present = any(col in assigned for col in NUMERIC_COLS)
        if not description and not numeric_present:
            continue  # blank / noise line

        def joined(col: str) -> str | None:
            parts = assigned.get(col)
            return " ".join(c.text for c in parts) if parts else None

        serial_raw = parse_int_loose(joined(COL_SERIAL))
        auto_serial += 1
        serial_no = serial_raw if serial_raw is not None else auto_serial

        gst_rate = parse_decimal_loose(joined(COL_GST))
        quantity = parse_decimal_loose(joined(COL_QTY))
        unit = normalize_unit(joined(COL_UNIT))
        rate_excl = parse_decimal_loose(joined(COL_RATE))
        rate_incl = parse_decimal_loose(joined(COL_RATE_INCL))
        amount = parse_decimal_loose(joined(COL_AMOUNT))

        ambiguous = False
        if rate_excl is not None and rate_incl is not None:
            source_rate, taxable_rate = rate_incl, rate_excl
        elif rate_excl is not None:
            source_rate = taxable_rate = rate_excl
        elif rate_incl is not None:
            # Only a tax-inclusive rate was printed. Per TRD §6, do not
            # guess the exclusive basis — surface both and flag for review.
            source_rate = rate_incl
            if gst_rate is not None and gst_rate >= 0:
                taxable_rate = rate_incl / (1 + gst_rate / Decimal("100"))
            else:
                taxable_rate = rate_incl
            ambiguous = True
        elif quantity and amount and quantity != 0:
            source_rate = taxable_rate = (amount / quantity)
            ambiguous = True
        else:
            source_rate = taxable_rate = None

        if taxable_rate is not None and quantity is not None and amount is not None:
            calculated = quantity * taxable_rate
            if abs(calculated - amount) > Decimal("1.00"):
                ambiguous = True

        all_row_cells = [c for cs in assigned.values() for c in cs]
        confidence = _row_confidence(all_row_cells)
        if ambiguous:
            confidence = min(confidence, 0.5)

        items.append(
            CandidateItem(
                serial_no=serial_no,
                description=description or "(unspecified)",
                hsn_sac=joined(COL_HSN),
                gst_rate=gst_rate,
                quantity=quantity,
                unit=unit,
                source_rate=source_rate,
                taxable_rate=taxable_rate,
                extracted_amount=amount,
                confidence=confidence,
                ambiguous=ambiguous,
            )
        )
    return items
