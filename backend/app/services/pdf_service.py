"""PDF generation. PRD FR-11, TRD §14.

Scenario PDFs use the JPEGs in ``backend/scenarios`` as full-page
templates. Scenario 1 keeps the current table-style layout, while
Scenario 2 and 3 use distinct table-free styles so they do not look
similar to each other.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from app.core.config import settings
from app.models.bill import Bill
from app.models.scenario import TYPE_BASELINE, Scenario
from app.utils.file_validation import sanitize_output_filename

PAGE_WIDTH, PAGE_HEIGHT = A4
CONTENT_LEFT = 18 * mm
CONTENT_RIGHT = PAGE_WIDTH - 18 * mm
CONTENT_WIDTH = CONTENT_RIGHT - CONTENT_LEFT

_styles = getSampleStyleSheet()

_table_cell_style = ParagraphStyle(
    "TableCell",
    parent=_styles["Normal"],
    fontName="Helvetica",
    fontSize=8.5,
    leading=10,
    textColor=colors.black,
)
_table_cell_bold_style = ParagraphStyle(
    "TableCellBold",
    parent=_styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=8.5,
    leading=10,
    textColor=colors.black,
)
_scenario2_product_style = ParagraphStyle(
    "Scenario2Product",
    parent=_styles["Normal"],
    fontName="Times-Roman",
    fontSize=11,
    leading=13,
    textColor=colors.HexColor("#1f2937"),
)
_scenario2_rate_style = ParagraphStyle(
    "Scenario2Rate",
    parent=_styles["Normal"],
    fontName="Times-Bold",
    fontSize=11,
    leading=13,
    textColor=colors.HexColor("#0f172a"),
)
_scenario2_label_style = ParagraphStyle(
    "Scenario2Label",
    parent=_styles["Normal"],
    fontName="Helvetica",
    fontSize=8,
    leading=10,
    textColor=colors.HexColor("#6b7280"),
)
_scenario2_total_style = ParagraphStyle(
    "Scenario2Total",
    parent=_styles["Normal"],
    fontName="Times-Bold",
    fontSize=13,
    leading=15,
    alignment=1,
    textColor=colors.HexColor("#111827"),
)
_scenario3_product_style = ParagraphStyle(
    "Scenario3Product",
    parent=_styles["Normal"],
    fontName="Courier-Bold",
    fontSize=10.5,
    leading=12,
    textColor=colors.HexColor("#111111"),
)
_scenario3_rate_style = ParagraphStyle(
    "Scenario3Rate",
    parent=_styles["Normal"],
    fontName="Courier",
    fontSize=10.5,
    leading=12,
    textColor=colors.HexColor("#7c2d12"),
)
_scenario3_total_style = ParagraphStyle(
    "Scenario3Total",
    parent=_styles["Normal"],
    fontName="Courier-Bold",
    fontSize=12,
    leading=14,
    alignment=1,
    textColor=colors.HexColor("#0f172a"),
)
_scenario3_desc_style = ParagraphStyle(
    "Scenario3Desc",
    parent=_styles["Normal"],
    fontName="Helvetica",
    fontSize=10.5,
    leading=12,
    textColor=colors.HexColor("#111827"),
)
_scenario3_amount_style = ParagraphStyle(
    "Scenario3Amount",
    parent=_styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=10.5,
    leading=12,
    textColor=colors.HexColor("#0f172a"),
)


def _first_line_baseline_offset(style: ParagraphStyle) -> float:
    """Distance below a Paragraph's top edge where its first text baseline falls.

    A Paragraph draws each line's baseline near the bottom of its ``leading``
    slot (offset by the font's descent), not at the slot's top edge. Plain
    ``drawString``/``drawRightString`` calls that need to sit on the same
    visual line as a Paragraph (e.g. a serial number next to a wrapped
    description) must use this offset instead of a guessed constant.
    """
    _, descent = pdfmetrics.getAscentDescent(style.fontName, style.fontSize)
    return style.leading - abs(descent)


_scenario2_row_baseline_offset = _first_line_baseline_offset(_scenario2_product_style)
_scenario3_row_baseline_offset = _first_line_baseline_offset(_scenario3_desc_style)


def _draw_tracked_string(
    c: canvas.Canvas,
    x: float,
    y: float,
    text: str,
    font_name: str,
    font_size: float,
    char_space: float,
    color: colors.Color,
    align: str = "left",
) -> None:
    """Draw text with letter-spacing (canvas.Canvas has no public setCharSpace)."""
    width = pdfmetrics.stringWidth(text, font_name, font_size) + char_space * max(len(text) - 1, 0)
    start_x = x - width if align == "right" else x
    text_obj = c.beginText(start_x, y)
    text_obj.setFont(font_name, font_size)
    text_obj.setFillColor(color)
    text_obj.setCharSpace(char_space)
    text_obj.textOut(text)
    c.drawText(text_obj)


def _money(value: Decimal) -> str:
    return f"Rs. {value:,.2f}"


def _filename_for(scenario: Scenario) -> str:
    if scenario.scenario_type == TYPE_BASELINE:
        return "baseline.pdf"
    label = scenario.label.lower()
    if "scenario b" in label:
        return "scenario-b.pdf"
    if "scenario c" in label:
        return "scenario-c.pdf"
    return sanitize_output_filename(scenario.label) + ".pdf"


def _template_path_for(scenario: Scenario) -> Path:
    label = scenario.label.lower()
    if scenario.scenario_type == TYPE_BASELINE:
        return settings.scenarios_dir / "scenario_11.jpeg"
    if "scenario c" in label:
        return settings.scenarios_dir / "scenario_33.jpeg"
    if "scenario b" in label:
        return settings.scenarios_dir / "scenario_22.jpeg"
    return settings.scenarios_dir / "scenario_11.jpeg"


def _draw_template_background(c: canvas.Canvas, template_path: Path) -> None:
    image = ImageReader(str(template_path))
    c.drawImage(image, 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT, mask="auto")


def _draw_paragraph(c: canvas.Canvas, text: str, style: ParagraphStyle, x: float, y: float, width: float) -> float:
    para = Paragraph(text, style)
    _, height = para.wrap(width, PAGE_HEIGHT)
    para.drawOn(c, x, y - height)
    return height


def _build_item_table(scenario: Scenario) -> Table:
    rows: list[list[Paragraph]] = [
        [
            Paragraph("<b>#</b>", _table_cell_bold_style),
            Paragraph("<b>Product</b>", _table_cell_bold_style),
            Paragraph("<b>Rate</b>", _table_cell_bold_style),
        ]
    ]

    for idx, item in enumerate(scenario.items, start=1):
        rows.append(
            [
                Paragraph(str(idx), _table_cell_style),
                Paragraph(item.description, _table_cell_style),
                Paragraph(_money(item.adjusted_rate), _table_cell_style),
            ]
        )

    table = Table(rows, colWidths=[12 * mm, 118 * mm, 34 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe4f0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111111")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#888888")),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _draw_scenario1(c: canvas.Canvas, scenario: Scenario, template_path: Path) -> None:
    table = _build_item_table(scenario)
    table_top = PAGE_HEIGHT - 75 * mm
    table_bottom_limit = 105
    available_height = table_top - table_bottom_limit

    _, table_height = table.wrap(CONTENT_WIDTH, PAGE_HEIGHT)

    while table_height > available_height:
        parts = table.split(CONTENT_WIDTH, available_height)
        if len(parts) < 2:
            break  # a single row taller than a page; nothing more we can do
        head, table = parts
        _, head_height = head.wrap(CONTENT_WIDTH, PAGE_HEIGHT)
        head.drawOn(c, CONTENT_LEFT, table_top - head_height)

        c.showPage()
        if template_path.exists():
            _draw_template_background(c, template_path)

        _, table_height = table.wrap(CONTENT_WIDTH, PAGE_HEIGHT)

    table.drawOn(c, CONTENT_LEFT, max(table_bottom_limit, table_top - table_height))


def _draw_scenario2(c: canvas.Canvas, scenario: Scenario, template_path: Path) -> None:
    top_y = PAGE_HEIGHT - 72 * mm
    left_x = CONTENT_LEFT
    serial_width = 8 * mm
    desc_x = left_x + serial_width
    rate_x = CONTENT_RIGHT
    row_gap = 14 * mm
    bottom_limit = 25 * mm  # scenario_22.jpeg has no footer artwork; just clear the physical page edge

    row_top = top_y
    for idx, item in enumerate(scenario.items, start=1):
        desc_para = Paragraph(item.description, _scenario2_product_style)
        _, desc_height = desc_para.wrap(CONTENT_WIDTH - 35 * mm - serial_width, PAGE_HEIGHT)

        if row_top - desc_height < bottom_limit:
            c.showPage()
            if template_path.exists():
                _draw_template_background(c, template_path)
            row_top = top_y

        baseline_y = row_top - _scenario2_row_baseline_offset

        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawString(left_x, baseline_y, f"{idx}.")

        desc_para.drawOn(c, desc_x, row_top - desc_height)

        c.setFont(_scenario2_rate_style.fontName, _scenario2_rate_style.fontSize)
        c.setFillColor(_scenario2_rate_style.textColor)
        c.drawRightString(rate_x, baseline_y, _money(item.adjusted_rate))

        row_top -= row_gap


def _draw_scenario3(c: canvas.Canvas, scenario: Scenario, template_path: Path) -> None:
    left_x = CONTENT_LEFT
    right_x = CONTENT_RIGHT
    top_y = PAGE_HEIGHT - 54 * mm
    row_gap = 14 * mm
    serial_width = 8 * mm
    desc_x = left_x + serial_width
    # scenario_33.jpeg's "DELIVERING your SATISFACTION" footer artwork starts ~260mm
    # from the top (measured directly from the template image); keep rows above it.
    bottom_limit = PAGE_HEIGHT - 245 * mm

    def draw_column_header(y: float) -> None:
        header_color = colors.HexColor("#0f172a")
        _draw_tracked_string(c, desc_x, y - 2, "DESCRIPTION", "Helvetica-Bold", 9, 0.8, header_color)
        _draw_tracked_string(c, right_x, y - 2, "AMOUNT", "Helvetica-Bold", 9, 0.8, header_color, align="right")

    draw_column_header(top_y)
    row_top = top_y - 10 * mm

    for idx, item in enumerate(scenario.items, start=1):
        desc_para = Paragraph(item.description, _scenario3_desc_style)
        _, desc_height = desc_para.wrap(CONTENT_WIDTH - 34 * mm - serial_width, PAGE_HEIGHT)

        if row_top - desc_height < bottom_limit:
            c.showPage()
            if template_path.exists():
                _draw_template_background(c, template_path)
            draw_column_header(top_y)
            row_top = top_y - 10 * mm

        baseline_y = row_top - _scenario3_row_baseline_offset

        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(left_x, baseline_y, f"{idx}.")

        desc_para.drawOn(c, desc_x, row_top - desc_height)

        c.setFont(_scenario3_amount_style.fontName, _scenario3_amount_style.fontSize)
        c.setFillColor(_scenario3_amount_style.textColor)
        c.drawRightString(right_x, baseline_y, _money(item.adjusted_rate))

        row_top -= row_gap

def generate_scenario_pdf(bill: Bill, scenario: Scenario) -> Path:
    out_dir = settings.generated_dir / bill.id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _filename_for(scenario)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    c.setTitle(scenario.label)

    template_path = _template_path_for(scenario)
    if template_path.exists():
        _draw_template_background(c, template_path)

    label = scenario.label.lower()
    if scenario.scenario_type == TYPE_BASELINE or "scenario a" in label:
        _draw_scenario1(c, scenario, template_path)
    elif "scenario c" in label:
        _draw_scenario3(c, scenario, template_path)
    else:
        _draw_scenario2(c, scenario, template_path)

    c.showPage()
    c.save()
    return out_path


def hash_file(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest()
