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
    r"terms\s*(&|and)\s*conditions|declaration|authoris|signature|bank\s*details|"
    r"\bc\s*[\.\s]*g\s*[\.\s]*s\s*[\.\s]*t\b|\bs\s*[\.\s]*g\s*[\.\s]*s\s*[\.\s]*t\b|\bi\s*[\.\s]*g\s*[\.\s]*s\s*[\.\s]*t\b|"
    r"\bcgst\b|\bsgst\b|\bigst\b|\bround\b|rounding|amount\s*chargeable|taxable\s*value|taxable\s*amount|"
    r"company.*pan|subject\s*to|e\s*&\s*o\s*e|thank\s*you)",
    re.IGNORECASE,
)

MIN_HEADER_MATCHES = 2


def _normalize_phrase(text: str) -> str:
    return re.sub(r"[^a-z0-9%]", "", text.lower())


def classify_header_cell(text: str) -> str | None:
    """Map a cell's text to a column type with robust alias matching."""
    norm = _normalize_phrase(text)
    if not norm:
        return None

    # --- GST / tax rate (Check FIRST so 'GST Rate' is never classified as Rate) ---
    if "gst" in norm or "cgst" in norm or "sgst" in norm or "igst" in norm or "taxrate" in norm or "taxper" in norm or norm in ("vat", "tax%", "gst%"):
        return COL_GST

    # --- HSN / SAC ---
    if "hsn" in norm or "sac" in norm or norm in ("code", "commodity"):
        return COL_HSN

    # --- Serial number ---
    if norm in ("no", "sr", "srno", "sl", "slno", "sno", "itemno", "slno", "#", "si", "sino") or "serial" in norm:
        return COL_SERIAL

    # --- Description ---
    if (
        "desc" in norm
        or "particular" in norm
        or "item" in norm
        or "goods" in norm
        or "product" in norm
        or "service" in norm
        or "article" in norm
        or "material" in norm
        or "name" in norm
        or "details" in norm
        or norm in ("particulrs", "particlr", "itm", "dsc")
    ):
        return COL_DESCRIPTION

    # --- Quantity ---
    if "qty" in norm or "quantity" in norm or "qnty" in norm or "qnt" in norm or norm in ("qty", "qy", "qnt", "units", "nos", "pcs"):
        return COL_QTY

    # --- Unit ---
    if "uom" in norm or norm in ("per", "unit", "uom", "un", "measure"):
        return COL_UNIT

    # --- Rate (Incl. of Tax) / MRP ---
    if "incl" in norm or "mrp" in norm or "inclusive" in norm:
        return COL_RATE_INCL

    # --- Rate / Price (Exclusive / Taxable) ---
    if "rate" in norm or "price" in norm or "prc" in norm or norm in ("rat", "prc", "pr", "cost", "unitprice"):
        return COL_RATE

    # --- Taxable amount ---
    if "taxable" in norm and ("value" in norm or "amount" in norm or "amt" in norm):
        return COL_AMOUNT

    # --- Amount / total ---
    if "amount" in norm or "total" in norm or "value" in norm or "amt" in norm or norm in ("amnt", "amou", "val", "netamt", "gross"):
        return COL_AMOUNT

    return None


@dataclass
class TableHeader:
    line_index: int
    columns: dict[str, float]  # column_type -> center_x


def find_header(lines: list[OcrLine]) -> TableHeader | None:
    """Locate the table header row by scoring each line for recognised column
    keywords.
    """
    best: TableHeader | None = None
    best_score = 0

    for idx, line in enumerate(lines):
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

        # Check for dual rate columns (Rate Incl vs Rate Excl)
        rate_entries = [entry for entry in cell_info if entry[2] in (COL_RATE, COL_RATE_INCL)]
        if len(rate_entries) == 2:
            rate_entries.sort(key=lambda e: e[0])
            first_x, first_text, _ = rate_entries[0]
            second_x, second_text, _ = rate_entries[1]

            first_is_incl = "incl" in first_text.lower() or "mrp" in first_text.lower()
            second_is_incl = "incl" in second_text.lower() or "mrp" in second_text.lower()
            if not first_is_incl and not second_is_incl:
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

    return _find_header_heuristic(lines)


def _is_data_line(line: OcrLine) -> bool:
    cells = line.cells()
    if not cells:
        return False
    numeric_count = sum(1 for c in cells if parse_decimal_loose(c.text) is not None)
    return numeric_count >= 1


def _find_header_heuristic(lines: list[OcrLine]) -> TableHeader | None:
    for idx in range(len(lines) - 2):
        run = sum(1 for l in lines[idx + 1: idx + 4] if _is_data_line(l))
        if run >= 2:
            data_line = lines[idx + 1]
            cells = data_line.cells()
            if not cells:
                continue
            n = len(cells)

            if n <= 3:
                col_types = [COL_DESCRIPTION, COL_QTY, COL_AMOUNT]
            elif n == 4:
                col_types = [COL_DESCRIPTION, COL_QTY, COL_RATE, COL_AMOUNT]
            elif n == 5:
                col_types = [COL_DESCRIPTION, COL_HSN, COL_QTY, COL_RATE, COL_AMOUNT]
            elif n == 6:
                col_types = [COL_DESCRIPTION, COL_HSN, COL_GST, COL_QTY, COL_RATE, COL_AMOUNT]
            else:
                col_types = [COL_DESCRIPTION, COL_HSN, COL_GST, COL_QTY, COL_RATE, COL_RATE_INCL, COL_AMOUNT]

            columns: dict[str, float] = {}
            for i, cell in enumerate(cells[:len(col_types)]):
                columns[col_types[i]] = cell.center_x

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
    confidence: float
    ambiguous: bool = field(default=False)


def _row_confidence(cells: list[OcrCell]) -> float:
    confs = [c.confidence for c in cells if c.words]
    if not confs:
        return 0.0
    return max(0.0, min(1.0, (sum(confs) / len(confs)) / 100.0))


def _parse_headerless_fallback(lines: list[OcrLine]) -> list[CandidateItem]:
    """Fallback row scanner for receipts or bills without standard column headers."""
    items: list[CandidateItem] = []
    auto_serial = 0

    for line in lines:
        if STOP_LINE_RE.search(line.text):
            break
        cells = line.cells()
        if not cells:
            continue

        decimals: list[tuple[int, Decimal]] = []
        for idx, c in enumerate(cells):
            val = parse_decimal_loose(c.text)
            if val is not None and val > 0:
                decimals.append((idx, val))

        if not decimals:
            if items and len(cells) == 1 and not re.search(r"^\d+$", cells[0].text):
                items[-1].description += f" {cells[0].text}"
            continue

        desc_cells = [cells[i] for i in range(len(cells)) if i not in [d[0] for d in decimals]]
        desc_text = " ".join(c.text for c in desc_cells).strip()

        rate_val = decimals[-1][1]
        qty_val = decimals[0][1] if len(decimals) >= 2 else Decimal("1")
        if len(decimals) >= 3:
            rate_val = decimals[-2][1]

        auto_serial += 1
        items.append(
            CandidateItem(
                serial_no=auto_serial,
                description=desc_text or f"Item {auto_serial}",
                hsn_sac=None,
                gst_rate=Decimal("0"),
                quantity=qty_val,
                unit=None,
                source_rate=rate_val,
                taxable_rate=rate_val,
                extracted_amount=decimals[-1][1],
                confidence=0.70,
                ambiguous=False,
            )
        )

    return items


def parse_table(lines: list[OcrLine]) -> list[CandidateItem]:
    header = find_header(lines)
    if header is None:
        return _parse_headerless_fallback(lines)

    items: list[CandidateItem] = []
    auto_serial = 0
    for line in lines[header.line_index + 1:]:
        if STOP_LINE_RE.search(line.text):
            break
        norm_line = re.sub(r"[^a-z]", "", line.text.lower())
        if any(w in norm_line for w in ("cgst", "sgst", "igst", "roundingoff", "roundoff", "grandtotal", "amountinwords", "termsandconditions")):
            break

        cells = line.cells()
        if not cells:
            continue

        assigned = _assign_cells_to_columns(cells, header.columns)
        description = " ".join(c.text for c in assigned.get(COL_DESCRIPTION, [])).strip()
        numeric_present = any(col in assigned for col in NUMERIC_COLS)

        if not description and not numeric_present:
            continue

        # If description is a single letter or pure noise and no valid rate
        if len(re.sub(r"[^a-zA-Z0-9]", "", description)) <= 1 and not numeric_present:
            continue

        def joined(col: str) -> str | None:
            parts = assigned.get(col)
            return " ".join(c.text for c in parts) if parts else None

        rate_excl = parse_decimal_loose(joined(COL_RATE))
        rate_incl = parse_decimal_loose(joined(COL_RATE_INCL))
        amount = parse_decimal_loose(joined(COL_AMOUNT))
        quantity = parse_decimal_loose(joined(COL_QTY))

        # Check if this is a multiline description continuation of the previous row
        if not numeric_present and description and items and rate_excl is None and amount is None:
            items[-1].description += f" {description}"
            continue

        serial_raw = parse_int_loose(joined(COL_SERIAL))
        auto_serial += 1
        serial_no = serial_raw if serial_raw is not None else auto_serial

        gst_rate = parse_decimal_loose(joined(COL_GST))
        unit = normalize_unit(joined(COL_UNIT))

        ambiguous = False
        if rate_excl is not None and rate_incl is not None:
            source_rate, taxable_rate = rate_incl, rate_excl
        elif rate_excl is not None:
            source_rate = taxable_rate = rate_excl
        elif rate_incl is not None:
            source_rate = rate_incl
            if gst_rate is not None and gst_rate >= 0:
                taxable_rate = rate_incl / (1 + gst_rate / Decimal("100"))
            else:
                taxable_rate = rate_incl
            ambiguous = True
        elif quantity and amount and quantity != 0:
            source_rate = taxable_rate = (amount / quantity)
            ambiguous = True
        elif amount is not None:
            source_rate = taxable_rate = amount
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

    if not items:
        return _parse_headerless_fallback(lines)

    return items
