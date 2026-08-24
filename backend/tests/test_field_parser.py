from app.services.field_parser import _find_date_in_text, extract_buyer_name, extract_gstin, parse_header_fields
from app.services.line_grouping import group_lines
from app.services.ocr.engine import OcrWord, full_text


def _word(text: str, left: int, top: int) -> OcrWord:
    return OcrWord(
        text=text,
        confidence=90.0,
        left=left,
        top=top,
        width=len(text) * 8,
        height=14,
        line_num=0,
        block_num=0,
        par_num=0,
    )


def test_vendor_name_and_address_stay_within_their_own_column():
    """Regression guard: a boxed multi-column invoice header (vendor block
    beside an Invoice No./Dated block beside a Delivery Note block, all on
    the same printed row) must not have field_parser read across columns.
    `group_lines` clusters by y-position only, so a naive `line.text` read
    spans every column; the fix scopes vendor_name/vendor_address to the
    line's leftmost x-gap-clustered cell instead.
    """
    rows = [
        [("CFF", 10), ("Invoice", 300), ("No.", 360), ("Dated", 600)],
        [("PAL", 10), ("WAS", 45), ("MOD", 80), ("BHIWANI", 115), ("472", 300), ("2-May-26", 600)],
        [("Contact", 10), (":", 80), ("9813291533", 95)],
    ]
    words = [_word(text, left, row_idx * 20) for row_idx, row in enumerate(rows) for text, left in row]
    lines = group_lines(words)

    fields = parse_header_fields(lines, full_text(words))

    assert fields.vendor_name == "CFF"
    assert fields.vendor_name is not None and "Invoice No" not in fields.vendor_name
    assert fields.vendor_address is not None
    assert "Dated" not in fields.vendor_address
    assert "472" not in fields.vendor_address
    assert fields.vendor_phone == "9813291533"


def test_gstin_regex_matches_real_15_character_gstin():
    # Regression guard: the pattern previously had one extra character
    # group and could never match a real (always 15-character) GSTIN.
    assert extract_gstin("GSTIN: 07ABCDE1234F1Z5") == "07ABCDE1234F1Z5"
    assert extract_gstin("GSTIN-06AEWPK0704K1ZB") == "06AEWPK0704K1ZB"


def test_buyer_name_extracted_inline_after_label():
    rows = [[("Bill", 10), ("To:", 60), ("G.M.S.", 110), ("Sec-13", 145), ("HUDA", 195)]]
    words = [_word(text, left, 0) for text, left in rows[0]]
    lines = group_lines(words)

    assert extract_buyer_name(lines) == "G.M.S. Sec-13 HUDA"


def test_buyer_name_extracted_from_line_below_label():
    rows = [
        [("Buyer", 10)],
        [("Acme", 10), ("Traders", 45)],
    ]
    words = [_word(text, left, row_idx * 20) for row_idx, row in enumerate(rows) for text, left in row]
    lines = group_lines(words)

    assert extract_buyer_name(lines) == "Acme Traders"


def test_buyer_name_none_when_no_label_present():
    # Never fabricated when the document doesn't actually print a buyer/bill-to label.
    words = [_word("Random", 10, 0), _word("Text", 90, 0)]
    lines = group_lines(words)

    assert extract_buyer_name(lines) is None


def test_date_parsing_supports_month_name_format():
    # Regression guard: "D-Mon-YY" (common on Indian invoices, e.g.
    # "29-Jul-26") previously fell through the purely-numeric DATE_RE and
    # left the Ref No./Date line blank on the generated PDF.
    from datetime import date

    assert _find_date_in_text("2-May-26") == date(2026, 5, 2)
    assert _find_date_in_text("Dated 29-Jul-26") == date(2026, 7, 29)
    assert _find_date_in_text("Date: 29/07/2026") == date(2026, 7, 29)
