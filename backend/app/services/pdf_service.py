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


def _draw_scenario1(c: canvas.Canvas, scenario: Scenario) -> None:
    table = _build_item_table(scenario)
    _, table_height = table.wrap(CONTENT_WIDTH, PAGE_HEIGHT)
    table_top = PAGE_HEIGHT - 75 * mm
    table_bottom_limit = 105
    table_y = max(table_bottom_limit, table_top - table_height)
    table.drawOn(c, CONTENT_LEFT, table_y)


def _draw_scenario2(c: canvas.Canvas, scenario: Scenario) -> None:
    top_y = PAGE_HEIGHT - 72 * mm
    left_x = CONTENT_LEFT
    rate_x = CONTENT_RIGHT
    row_gap = 14 * mm

    for idx, item in enumerate(scenario.items):
        row_top = top_y - idx * row_gap
        desc_para = Paragraph(item.description, _scenario2_product_style)
        _, desc_height = desc_para.wrap(CONTENT_WIDTH - 35 * mm, PAGE_HEIGHT)
        desc_para.drawOn(c, left_x, row_top - desc_height)

        c.setFont(_scenario2_rate_style.fontName, _scenario2_rate_style.fontSize)
        c.setFillColor(_scenario2_rate_style.textColor)
        c.drawRightString(rate_x, row_top - 3, _money(item.adjusted_rate))

        c.setStrokeColor(colors.HexColor("#cbd5e1"))
        c.setLineWidth(0.7)
        c.line(left_x, row_top - row_gap + 1, rate_x, row_top - row_gap + 1)

def _draw_scenario3(c: canvas.Canvas, scenario: Scenario) -> None:
    left_x = CONTENT_LEFT
    right_x = CONTENT_RIGHT
    top_y = PAGE_HEIGHT - 84 * mm
    row_gap = 14 * mm

    c.setStrokeColor(colors.HexColor("#334155"))
    c.setLineWidth(1.0)
    c.line(left_x, top_y + 5, right_x, top_y + 5)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(left_x, top_y - 2, "Description")
    c.drawRightString(right_x, top_y - 2, "Amount")
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.line(left_x, top_y - 5, right_x, top_y - 5)

    for idx, item in enumerate(scenario.items):
        row_top = top_y - 10 * mm - idx * row_gap
        desc_para = Paragraph(item.description, _scenario3_desc_style)
        _, desc_height = desc_para.wrap(CONTENT_WIDTH - 34 * mm, PAGE_HEIGHT)
        desc_para.drawOn(c, left_x, row_top - desc_height)

        c.setFont(_scenario3_amount_style.fontName, _scenario3_amount_style.fontSize)
        c.setFillColor(_scenario3_amount_style.textColor)
        c.drawRightString(right_x, row_top - 2, _money(item.adjusted_rate))

        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.setLineWidth(0.7)
        c.line(left_x, row_top - row_gap + 2, right_x, row_top - row_gap + 2)

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
        _draw_scenario1(c, scenario)
    elif "scenario c" in label:
        _draw_scenario3(c, scenario)
    else:
        _draw_scenario2(c, scenario)

    c.showPage()
    c.save()
    return out_path


def hash_file(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest()
