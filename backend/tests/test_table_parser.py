from decimal import Decimal

from app.services.line_grouping import group_lines
from app.services.ocr_service import OcrWord
from app.services.table_parser import parse_table

LINE_HEIGHT = 30
CHAR_WIDTH = 12
WORD_GAP = 15  # normal space between words within one cell
COLUMN_STEP = 320  # generous column pitch so columns never collide with cell content


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
