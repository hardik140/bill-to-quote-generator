"""PDF generation. PRD FR-11, TRD §14.

Scenario B/C PDFs must visibly carry the simulation disclaimer and must
never include fabricated vendor signatures/seals/GST certificates/bank
details (PRD compliance note, DATA.md §16 rule 10).
"""

import hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.models.bill import Bill
from app.models.scenario import TYPE_BASELINE, Scenario
from app.utils.file_validation import sanitize_output_filename

_styles = getSampleStyleSheet()
_title_style = ParagraphStyle("QuoteTitle", parent=_styles["Title"], fontSize=16)
_disclaimer_style = ParagraphStyle(
    "Disclaimer",
    parent=_styles["Normal"],
    fontSize=10,
    textColor=colors.HexColor("#8a1f11"),
    borderColor=colors.HexColor("#8a1f11"),
    borderWidth=1,
    borderPadding=6,
    backColor=colors.HexColor("#fdecea"),
    spaceBefore=8,
    spaceAfter=8,
)
_baseline_note_style = ParagraphStyle(
    "BaselineNote",
    parent=_styles["Normal"],
    fontSize=10,
    textColor=colors.HexColor("#0f5132"),
    spaceBefore=8,
    spaceAfter=8,
)


def _filename_for(scenario: Scenario) -> str:
    if scenario.scenario_type == TYPE_BASELINE:
        return "baseline.pdf"
    label = scenario.label.lower()
    if "scenario b" in label:
        return "scenario-b.pdf"
    if "scenario c" in label:
        return "scenario-c.pdf"
    return sanitize_output_filename(scenario.label) + ".pdf"


def _money(value: Decimal) -> str:
    return f"Rs. {value:,.2f}"


def generate_scenario_pdf(bill: Bill, scenario: Scenario) -> Path:
    out_dir = settings.generated_dir / bill.id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _filename_for(scenario)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
    )

    elements = []
    elements.append(Paragraph(scenario.label, _title_style))
    elements.append(
        Paragraph(f"Generated: {datetime.utcnow().strftime('%d-%b-%Y %H:%M UTC')}", _styles["Normal"])
    )
    elements.append(Spacer(1, 6))

    if scenario.scenario_type == TYPE_BASELINE:
        elements.append(Paragraph(scenario.disclaimer, _baseline_note_style))
    else:
        elements.append(Paragraph(f"<b>{scenario.disclaimer}</b>", _disclaimer_style))
        elements.append(
            Paragraph(
                f"Markup applied over baseline rate: {scenario.markup_percent}%. "
                "This document is an internally generated estimate for budgeting "
                "and comparison only and does not represent a genuine vendor quotation.",
                _styles["Normal"],
            )
        )

    elements.append(Spacer(1, 10))

    header_rows = [
        ["Vendor (source document)", bill.vendor_name or "-"],
        ["Invoice / Reference No.", bill.invoice_number or "-"],
        ["Invoice Date", bill.invoice_date.isoformat() if bill.invoice_date else "-"],
        ["Buyer", bill.buyer_name or "-"],
        ["Currency", bill.currency],
        ["Rounding Policy", scenario.rounding_mode],
    ]
    header_table = Table(header_rows, colWidths=[55 * mm, 110 * mm])
    header_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    elements.append(header_table)
    elements.append(Spacer(1, 12))

    item_header = ["#", "Description", "Qty", "Unit", "Rate", "Tax", "Amount"]
    item_rows = [item_header]
    for idx, item in enumerate(scenario.items, start=1):
        item_rows.append(
            [
                str(idx),
                item.description,
                f"{item.quantity:g}" if item.quantity == item.quantity.to_integral_value() else str(item.quantity),
                item.unit or "-",
                _money(item.adjusted_rate),
                _money(item.tax_amount),
                _money(item.total_amount),
            ]
        )

    item_table = Table(item_rows, colWidths=[8 * mm, 62 * mm, 15 * mm, 15 * mm, 25 * mm, 22 * mm, 25 * mm], repeatRows=1)
    item_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(item_table)
    elements.append(Spacer(1, 10))

    summary_rows = [
        ["Subtotal", _money(scenario.subtotal)],
        ["Tax", _money(scenario.tax_total)],
        ["Grand Total", _money(scenario.grand_total)],
    ]
    summary_table = Table(summary_rows, colWidths=[140 * mm, 32 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 16))

    footer_text = (
        "This document was generated locally for internal procurement, budgeting, "
        "comparison, and scenario-analysis purposes only."
        if scenario.scenario_type == TYPE_BASELINE
        else (
            "No vendor signature, seal, GSTIN, or bank detail on this document "
            "should be relied upon as authentic -- this is an internally generated "
            "simulation and must not be treated as a real vendor quotation."
        )
    )
    elements.append(Paragraph(footer_text, _styles["Italic"]))

    doc.build(elements)
    return out_path


def hash_file(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest()
