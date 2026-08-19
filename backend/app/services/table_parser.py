"""Line-item table extraction (FR-04). Column order is never assumed —
the header row is located and its column x-positions drive assignment of
every data row, per PRD FR-04 (\"must not assume every bill has the same
column order\").
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
    r"(grand\s*total|sub\s*total|^\s*total\b|total\s*amount|amount\s*in\s*words|"
    r"terms\s*(&|and)\s*conditions|declaration|authoris|bank\s*details|"
    r"\bc\s*\.?\s*g\s*\.?\s*s\s*\.?\s*t\b|\bs\s*\.?\s*g\s*\.?\s*s\s*\.?\s*t\b|\bi\s*\.?\s*g\s*\.?\s*s\s*\.?\s*t\b|"
    r"rounding\s*off|round\s*off|amount\s*chargeable|taxable\s*value|taxable\s*amount|"
    r"company.*pan|subject\s*to)",
    re.IGNORECASE,
)

# Lowered from 3: many real Indian bills have garbled header rows where only
# 2 column labels survive OCR cleanly (e.g. "Particulars" + "Amount").
MIN_HEADER_MATCHES = 2


def _normalize_phrase(text: str) -> str:
    return re.sub(r"[^a-z0-9%]", "", text.lower())


def classify_header_cell(text: str) -> str | None:
    """Map a cell's text to a column type.

    Uses both exact-normalized matching and substring fuzzy matching so that
    partially-garbled OCR output like "Desc", "Amt", "Qnty", "HSn",
    "Particulrs" still maps to the correct column type.
    """
    norm = _normalize_phrase(text)
    if not norm:
        return None

    # --- HSN / SAC ---
    if "hsn" in norm or "sac" in norm:
        return COL_HSN

    # --- Serial number ---
    if norm in ("no", "sr", "srno", "sl", "slno", "sno", "#") or "serial" in norm or norm == "sno":
        return COL_SERIAL

    # --- Description (fuzzy substrings) ---
    if (
        "desc" in norm
        or "particular" in norm
        or "item" in norm
        or "goods" in norm
        or "product" in norm
        or "name" in norm
        or norm in ("particulrs", "particlr", "itm", "dsc")
    ):
        return COL_DESCRIPTION

    # --- Quantity ---
    if "qty" in norm or "quantity" in norm or "qnty" in norm or "qnt" in norm or norm in ("qty", "qy", "qnt"):
        return COL_QTY

    # --- Unit ---
    if "uom" in norm or norm in ("per", "unit", "uom", "un"):
        return COL_UNIT

    # --- Rate / price / MRP ---
    if "rate" in norm or "price" in norm or "mrp" in norm or norm in ("rat", "prc", "pr"):
        if "gst" in norm or "taxrate" in norm or norm in ("rate%", "taxper", "tax%"):
            return COL_GST
        return COL_RATE_INCL if ("incl" in norm or "tax" in norm) else COL_RATE

    # --- GST / tax rate ---
    if (
        "gst" in norm
        or "cgst" in norm
        or "sgst" in norm
        or "igst" in norm
        or "taxrate" in norm
        or norm in ("gst%", "taxper")
    ):
        return COL_GST

    # --- Taxable amount (must check before generic amount/rate) ---
    if "taxable" in norm and ("value" in norm or "amount" in norm or "amt" in norm):
        return COL_AMOUNT

    # --- Amount / total ---
    if "amount" in norm or "total" in norm or "value" in norm or "amt" in norm or norm in ("amnt", "amou", "val"):
        return COL_AMOUNT

    return None


@dataclass
class TableHeader:
    line_index: int
    columns: dict[str, float]  # column_type -> center_x


def find_header(lines: list[OcrLine]) -> TableHeader | None:
    """Locate the table header row by scoring each line for recognised column
    keywords. Returns the best-scoring line that meets the minimum threshold.

    Handles multi-line wrapped headers (e.g. Rate on line 1 with '(Incl. of Tax)'
    on line 2) and disambiguates dual rate columns (Rate Incl vs Rate Excl).
    """
    best: TableHeader | None = None
    best_score = 0

    for idx, line in enumerate(lines):
        # Inspect whether the next line is a subheader (e.g. 'No', '(Incl. of Tax)', 'Rate')
        sub_cells: list[OcrCell] = []
        is_multiline_header = False
        if idx + 1 < len(lines) and not _is_data_line(lines[idx + 1]):
            candidate_sub = lines[idx + 1]
            sub_text = candidate_sub.text.lower()
            if any(k in sub_text for k in ("no", "incl", "tax", "rate", "code", "sac", "per", "uom")):
                sub_cells = candidate_sub.cells()
                is_multiline_header = True

        raw_cells = line.cells()
        cell_info: list[tuple[float, str, str | None]] = []

        for cell in raw_cells:
            text = cell.text
            # Merge with vertically aligned sub-cell if present
            if sub_cells:
                matched_sub = [
                    sc for sc in sub_cells
                    if abs(sc.center_x - cell.center_x) < 150.0
                    or (sc.left <= cell.right + 30 and sc.right >= cell.left - 30)
                ]
                if matched_sub:
                    text = text + " " + " ".join(sc.text for sc in matched_sub)
            col_type = classify_header_cell(text)
            cell_info.append((cell.center_x, text, col_type))

        # Check for dual rate columns (e.g. Rate Incl and Rate Excl)
        rate_entries = [entry for entry in cell_info if entry[2] in (COL_RATE, COL_RATE_INCL)]
        if len(rate_entries) >= 2:
            # Sort left to right
            rate_entries.sort(key=lambda e: e[0])
            first_x, first_text, _ = rate_entries[0]
            second_x, second_text, _ = rate_entries[1]

            second_is_incl = "incl" in second_text.lower()
            first_is_incl = "incl" in first_text.lower() or "tax" in first_text.lower()
            if not second_is_incl and not first_is_incl:
                # In standard Indian GST layouts, the first rate column (after Qty)
                # is Rate (Incl. of Tax), and the second is Rate (Excl. of Tax).
                first_is_incl = True

            new_cell_info = []
            for entry in cell_info:
                if entry[0] == first_x:
                    new_cell_info.append((first_x, first_text, COL_RATE_INCL if first_is_incl else COL_RATE))
                elif entry[0] == second_x:
                    new_cell_info.append((second_x, second_text, COL_RATE if first_is_incl else COL_RATE_INCL))
                else:
                    new_cell_info.append(entry)
            cell_info = new_cell_info

        columns: dict[str, float] = {}
        for cx, _, col_type in cell_info:
            if col_type and col_type not in columns:
                columns[col_type] = cx

        score = len(columns)
        has_core = COL_DESCRIPTION in columns and (
            COL_QTY in columns or COL_RATE in columns or COL_RATE_INCL in columns or COL_AMOUNT in columns
        )
        if score >= MIN_HEADER_MATCHES and has_core and score > best_score:
            best = TableHeader(line_index=idx + 1 if is_multiline_header else idx, columns=columns)
            best_score = score

    if best is not None:
        return best

    # --- Heuristic fallback ---
    return _find_header_heuristic(lines)


def _is_data_line(line: OcrLine) -> bool:
    """Return True if the line looks like a table data row (contains at least
    one decimal number among its cells)."""
    cells = line.cells()
    if not cells:
        return False
    numeric_count = sum(1 for c in cells if parse_decimal_loose(c.text) is not None)
    return numeric_count >= 1


def _find_header_heuristic(lines: list[OcrLine]) -> TableHeader | None:
    """Fallback: find the first line after which >= 3 consecutive data lines
    appear, and treat that line as the header. Assign synthetic column positions
    based on the x-positions of cells in the first data row below it.

    Column type assignment uses the count of cells in the data row and maps
    them to the most common Indian invoice column patterns:
      4 cols: description | qty+unit | rate | amount
      5 cols: description | hsn | qty+unit | rate | amount
      6 cols: serial+desc | hsn | gst | qty | rate | amount
      7 cols: serial+desc | hsn | gst | qty | rate_excl | rate_incl | amount
    """
    for idx in range(len(lines) - 3):
        run = sum(1 for l in lines[idx + 1: idx + 4] if _is_data_line(l))
        if run >= 3:
            # Use first data row to infer column x-positions
            data_line = lines[idx + 1]
            cells = data_line.cells()
            if not cells:
                continue
            n = len(cells)

            # Choose column type mapping based on cell count
            if n <= 3:
                col_types = [COL_DESCRIPTION, COL_QTY, COL_AMOUNT]
            elif n == 4:
                col_types = [COL_DESCRIPTION, COL_QTY, COL_RATE, COL_AMOUNT]
            elif n == 5:
                col_types = [COL_DESCRIPTION, COL_HSN, COL_QTY, COL_RATE, COL_AMOUNT]
            elif n == 6:
                col_types = [COL_DESCRIPTION, COL_HSN, COL_GST, COL_QTY, COL_RATE, COL_AMOUNT]
            else:
                # 7+ cols
                col_types = [COL_DESCRIPTION, COL_HSN, COL_GST, COL_QTY, COL_RATE, COL_RATE_INCL, COL_AMOUNT]
                if n > 7:
                    col_types = col_types[:n]  # truncate extra

            columns: dict[str, float] = {}
            for i, cell in enumerate(cells[:len(col_types)]):
                columns[col_types[i]] = cell.center_x

            # Only accept if we have at least description + a numeric column
            has_core = COL_DESCRIPTION in columns and any(
                c in columns for c in (COL_QTY, COL_RATE, COL_AMOUNT)
            )
            if has_core:
                return TableHeader(line_index=idx, columns=columns)
    return None



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
    for line in lines[header.line_index + 1:]:
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
