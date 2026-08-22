"""PDF generation. PRD FR-11, TRD §14.

Scenario PDFs now use the JPEGs in ``backend/scenarios`` as full-page
templates. The generated PDF overlays only the bill data requested by the
user: product lines, rates, and the total.
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
        return settings.scenarios_dir / "scenario_1.jpeg"
    if "scenario c" in label:
        return settings.scenarios_dir / "scenario_3.jpeg"
    if "scenario b" in label:
        return settings.scenarios_dir / "scenario_2.jpeg"
    return settings.scenarios_dir / "scenario_1.jpeg"


def _draw_template_background(c: canvas.Canvas, template_path: Path) -> None:
    image = ImageReader(str(template_path))
    c.drawImage(image, 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT, mask="auto")


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


def _draw_total_block(c: canvas.Canvas, scenario: Scenario) -> None:
    total = Table(
        [[Paragraph("<b>Total</b>", _table_cell_bold_style), Paragraph(_money(scenario.grand_total), _table_cell_bold_style)]],
        colWidths=[136 * mm, 34 * mm],
    )
    total.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.9, colors.HexColor("#222222")),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    width, height = total.wrap(CONTENT_WIDTH, PAGE_HEIGHT)
    total.drawOn(c, CONTENT_LEFT, 86)


def generate_scenario_pdf(bill: Bill, scenario: Scenario) -> Path:
    out_dir = settings.generated_dir / bill.id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _filename_for(scenario)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    c.setTitle(scenario.label)

    template_path = _template_path_for(scenario)
    if template_path.exists():
        _draw_template_background(c, template_path)

    table = _build_item_table(scenario)
    _, table_height = table.wrap(CONTENT_WIDTH, PAGE_HEIGHT)
    table_top = PAGE_HEIGHT - 75 * mm
    table_bottom_limit = 105
    table_y = max(table_bottom_limit, table_top - table_height)
    table.drawOn(c, CONTENT_LEFT, table_y)

    _draw_total_block(c, scenario)

    c.showPage()
    c.save()
    return out_path


def hash_file(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest()
