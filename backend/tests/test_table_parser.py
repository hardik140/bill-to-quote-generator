from decimal import Decimal

from app.services.line_grouping import group_lines
from app.services.ocr_service import OcrWord
from app.services.table_parser import parse_table

LINE_HEIGHT = 30
CHAR_WIDTH = 12
WORD_GAP = 15  # normal space between words within one cell
COLUMN_STEP = 500  # generous column pitch so columns never collide with cell content


def make_words(rows: list[list[str]], col_count: int) -> list[OcrWord]:
    """rows: list of rows, each a list of up to col_count cell strings, one
    cell per fixed-pitch column so column x-position is unambiguous."""
    col_lefts = [i * COLUMN_STEP for i in range(col_count)]
    words: list[OcrWord] = []
    for line_num, row in enumerate(rows):
        for col_idx, cell_text in enumerate(row):
            if not cell_text:
                continue
            x = col_lefts[col_idx]
            for token in cell_text.split(" "):
                width = len(token) * CHAR_WIDTH
                words.append(
                    OcrWord(
                        text=token,
                        confidence=92.0,
                        left=x,
                        top=line_num * LINE_HEIGHT,
                        width=width,
                        height=LINE_HEIGHT - 5,
                        line_num=line_num,
                        block_num=1,
                        par_num=1,
                    )
                )
                x += width + WORD_GAP
    return words


def test_standard_column_order():
    # Sr Desc HSN GST Qty Unit Rate Amount
    rows = [
        ["S.No", "Description", "HSN", "GST%", "Qty", "Unit", "Rate", "Amount"],
        ["1", "A4 Paper Rim 75 GSM", "4802", "18", "1", "RIM", "240.00", "240.00"],
        ["2", "Ball Pen Blue", "9608", "12", "10", "PCS", "8.00", "80.00"],
    ]
    words = make_words(rows, col_count=8)
    lines = group_lines(words)
    items = parse_table(lines)

    assert len(items) == 2
    assert items[0].description == "A4 Paper Rim 75 GSM"
    assert items[0].quantity == Decimal("1")
    assert items[0].taxable_rate == Decimal("240.00")
    assert items[0].gst_rate == Decimal("18")
    assert items[0].unit == "RIM"
    assert items[1].unit == "PCS"
    assert items[1].taxable_rate == Decimal("8.00")


def test_reordered_columns_still_parse_correctly():
    # Same data, but Amount/Rate/Unit/Qty swapped to the front vs. the
    # "standard" test above -- FR-04 requires this not to break parsing.
    # Sr Desc Amount Rate Unit Qty GST HSN
    rows = [
        ["S.No", "Description", "Amount", "Rate", "Unit", "Qty", "GST%", "HSN"],
        ["1", "A4 Paper Rim 75 GSM", "240.00", "240.00", "RIM", "1", "18", "4802"],
        ["2", "Ball Pen Blue", "80.00", "8.00", "PCS", "10", "12", "9608"],
    ]
    words = make_words(rows, col_count=8)
    lines = group_lines(words)
    items = parse_table(lines)

    assert len(items) == 2
    assert items[0].description == "A4 Paper Rim 75 GSM"
    assert items[0].quantity == Decimal("1")
    assert items[0].taxable_rate == Decimal("240.00")
    assert items[0].unit == "RIM"
    assert items[0].hsn_sac == "4802"


def test_tax_inclusive_rate_only_is_flagged_ambiguous():
    # Sr Desc Qty Unit "Rate (Incl. of Tax)" GST
    rows = [
        ["S.No", "Description", "Qty", "Unit", "Rate (Incl. of Tax)", "GST%"],
        ["1", "Stapler", "6", "PCS", "55.00", "18"],
    ]
    words = make_words(rows, col_count=6)
    lines = group_lines(words)
    items = parse_table(lines)

    assert len(items) == 1
    item = items[0]
    assert item.source_rate == Decimal("55.00")
    assert item.ambiguous is True
    assert item.confidence <= 0.5
    # taxable_rate derived as 55 / 1.18 -- must not just copy the inclusive rate
    assert item.taxable_rate != item.source_rate


def test_table_stops_at_total_line():
    rows = [
        ["S.No", "Description", "Qty", "Rate"],
        ["1", "Item One", "1", "100.00"],
        ["", "Grand Total", "", "100.00"],
        ["2", "Item Two (should not be parsed)", "1", "50.00"],
    ]
    words = make_words(rows, col_count=4)
    lines = group_lines(words)
    items = parse_table(lines)

    assert len(items) == 1
    assert items[0].description == "Item One"


def test_no_header_returns_empty():
    words = make_words([["random", "noise", "text"]], col_count=3)
    lines = group_lines(words)
    assert parse_table(lines) == []


def test_delhi_stationery_dual_rate_invoice():
    # Multi-line header with dual rate columns: Rate (Incl. of Tax) vs Rate (Excl. Tax)
    # Header Line 1: Sl | Description of Goods | HSN/SAC | GST Rate | Quantity | Rate | Rate | per | Amount
    # Header Line 2: No | | | | | (Incl. of Tax) | | |
    rows = [
        ["Sl", "Description of Goods", "HSN/SAC", "GST Rate", "Quantity", "Rate", "Rate", "per", "Amount"],
        ["No", "", "", "", "", "(Incl. of Tax)", "", "", ""],
        ["1", "Student Attendance Register No. 2", "4820", "18 %", "6 PCS.", "55.00", "46.61", "PCS.", "279.66"],
        ["2", "A4 Paper Rim 75 GSM", "4802", "18 %", "1 RIM", "240.00", "203.39", "RIM", "203.39"],
        ["3", "Teacher Attendance No. 2", "4820", "18 %", "1 PCS.", "180.00", "152.54", "PCS.", "152.54"],
        ["4", "Long Note Book 240 PG", "4820", "0 %", "5 PCS.", "115.00", "115.00", "PCS.", "575.00"],
        ["5", "Paste File", "4820", "18 %", "5 PCS.", "119.99", "101.69", "PCS.", "508.45"],
        ["14", "Kangaro Stapler HS-R-10", "8472", "18 %", "1 PCS.", "50.00", "42.37", "PCS.", "42.37"],
        ["15", "Kangaro 10 No. Staple Pin", "8305", "18 %", "3 PCS.", "9.99", "8.47", "PCS.", "25.41"],
        ["", "CGST", "", "", "", "", "", "", "154.45"],
        ["", "SGST", "", "", "", "", "", "", "154.45"],
        ["", "ROUNDING OFF", "", "", "", "", "", "", "0.13"],
        ["", "Total", "", "", "", "", "", "", "2600.00"],
    ]
    words = make_words(rows, col_count=9)
    lines = group_lines(words)
    items = parse_table(lines)

    assert len(items) == 7
    # Row 1: Student Attendance Register No. 2
    assert "Student Attendance Register No. 2" in items[0].description
    assert items[0].source_rate == Decimal("55.00")  # rate with GST
    assert items[0].taxable_rate == Decimal("46.61")  # rate WITHOUT GST (base rate)
    assert items[0].quantity == Decimal("6")
    assert items[0].extracted_amount == Decimal("279.66")

    # Row 2: A4 Paper Rim 75 GSM
    assert "A4 Paper Rim 75 GSM" in items[1].description
    assert items[1].taxable_rate == Decimal("203.39")

    # Row 4: Long Note Book 240 PG (0% GST)
    assert "Long Note Book 240 PG" in items[3].description
    assert items[3].taxable_rate == Decimal("115.00")

    # Row 6: Kangaro Stapler HS-R-10
    assert "Kangaro Stapler HS-R-10" in items[5].description
    assert items[5].taxable_rate == Decimal("42.37")

    # Row 7: Kangaro 10 No. Staple Pin
    assert "Kangaro 10 No. Staple Pin" in items[6].description
    assert items[6].taxable_rate == Decimal("8.47")


def test_clean_description():
    from app.services.extraction_service import _clean_description

    # Leading punctuated serial numbers are always stripped
    assert _clean_description("1. Student Attendance Register No. 2", 1) == "Student Attendance Register No. 2"
    assert _clean_description("14) Kangaro Stapler HS-R-10", 14) == "Kangaro Stapler HS-R-10"
    assert _clean_description("2 - A4 Paper Rim 75 GSM", 2) == "A4 Paper Rim 75 GSM"

    # Leading bare digit matching row serial number is stripped
    assert _clean_description("1 Student Attendance Register No. 2", 1) == "Student Attendance Register No. 2"
    assert _clean_description("4 Long Note Book 240 PG", 4) == "Long Note Book 240 PG"

    # Product names starting with numbers (not matching serial) are preserved
    assert _clean_description("2 Inch Binder Ring", 1) == "2 Inch Binder Ring"
    assert _clean_description("75 GSM Copier Paper", 2) == "75 GSM Copier Paper"


def test_stop_lines_extended():
    rows = [
        ["S.No", "Description", "Qty", "Rate"],
        ["1", "Item One", "1", "100.00"],
        ["", "SGST @ 9%", "", "9.00"],
        ["", "CGST @ 9%", "", "9.00"],
        ["", "Rounding Off", "", "-0.20"],
        ["", "Amount Chargeable (in words)", "", "118.00"],
        ["2", "Should Not Be Extracted", "1", "50.00"],
    ]
    words = make_words(rows, col_count=4)
    lines = group_lines(words)
    items = parse_table(lines)

    assert len(items) == 1
    assert items[0].description == "Item One"


