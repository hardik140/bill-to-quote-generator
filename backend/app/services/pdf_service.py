"""PDF generation. PRD FR-11, TRD §14.

Scenario B/C PDFs must visibly carry the simulation disclaimer and must
NEVER include a vendor's identity, GSTIN, logo, or contact details (PRD
compliance note, DATA.md §16 rule 10) -- only the Baseline PDF may show
the vendor letterhead, and only using data actually extracted from the
uploaded document. Nothing here may hardcode or fabricate a business
identity.
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
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.models.bill import Bill
from app.models.scenario import TYPE_BASELINE, Scenario
from app.services.preprocessing_service import HEADER_CROP_FILENAME
from app.utils.file_validation import sanitize_output_filename

_styles = getSampleStyleSheet()
_title_style = ParagraphStyle("QuoteTitle", parent=_styles["Title"], fontSize=16)
_vendor_name_style = ParagraphStyle(
    "VendorName", parent=_styles["Normal"], fontSize=14, fontName="Helvetica-Bold",
    textColor=colors.HexColor("#0f172a"), alignment=1,
)
_vendor_meta_style = ParagraphStyle(
    "VendorMeta", parent=_styles["Normal"], fontSize=9, fontName="Helvetica",
    textColor=colors.HexColor("#334155"), alignment=1,
)
_ref_date_style = ParagraphStyle(
    "RefDate", parent=_styles["Normal"], fontSize=9, fontName="Helvetica",
    textColor=colors.HexColor("#334155"),
)
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


def _build_vendor_letterhead(bill: Bill) -> list:
    """Baseline-only header block built strictly from what was extracted
    from *this* uploaded document. Any field that wasn't found is simply
    omitted -- never guessed, never filled with a placeholder identity."""
    elements: list = []

    header_crop = settings.images_dir / bill.document_id / HEADER_CROP_FILENAME
    if header_crop.exists():
        img = Image(str(header_crop), width=178 * mm, height=178 * mm * 0.22)
        img.hAlign = "CENTER"
        elements.append(img)
        elements.append(Spacer(1, 6))

    if bill.vendor_name:
        elements.append(Paragraph(bill.vendor_name, _vendor_name_style))

    meta_parts = []
    if bill.vendor_address:
        meta_parts.append(bill.vendor_address)
    if bill.vendor_phone:
        meta_parts.append(f"Phone: {bill.vendor_phone}")
    if bill.vendor_email:
        meta_parts.append(bill.vendor_email)
    if meta_parts:
        elements.append(Paragraph(" &bull; ".join(meta_parts), _vendor_meta_style))

    if bill.vendor_gstin:
        elements.append(Paragraph(f"<b>GSTIN:</b> {bill.vendor_gstin}", _vendor_meta_style))

    if elements:
        elements.append(Spacer(1, 6))

    ref_no = bill.invoice_number or "-"
    inv_date = bill.invoice_date.isoformat() if bill.invoice_date else "-"
    ref_row = Table(
        [[Paragraph(f"Ref. No. {ref_no}", _ref_date_style), Paragraph(f"Date {inv_date}", _ref_date_style)]],
        colWidths=[89 * mm, 89 * mm],
    )
    ref_row.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.75, colors.HexColor("#94a3b8")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor("#94a3b8")),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(ref_row)
    elements.append(Spacer(1, 10))
    return elements


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

    elements: list = []
    is_baseline = scenario.scenario_type == TYPE_BASELINE

    if is_baseline:
        # The only place a vendor identity may appear, and only what was
        # actually extracted from the uploaded document.
        elements.extend(_build_vendor_letterhead(bill))

    elements.append(Paragraph(scenario.label, _title_style))
    elements.append(
        Paragraph(f"Generated: {datetime.utcnow().strftime('%d-%b-%Y %H:%M UTC')}", _styles["Normal"])
    )
    elements.append(Spacer(1, 6))

    if is_baseline:
        elements.append(Paragraph(scenario.disclaimer, _baseline_note_style))
    else:
        # Scenario B/C: disclaimer only, never a vendor block of any kind.
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

    item_header = ["#", "Product", "Rate"]
    item_rows = [item_header]
    for idx, item in enumerate(scenario.items, start=1):
        item_rows.append([str(idx), item.description, _money(item.adjusted_rate)])

    item_table = Table(item_rows, colWidths=[12 * mm, 130 * mm, 36 * mm], repeatRows=1)
    item_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(item_table)
    elements.append(Spacer(1, 8))

    total_row = Table([["Total", _money(scenario.grand_total)]], colWidths=[142 * mm, 36 * mm])
    total_row.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.75, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(total_row)
    elements.append(Spacer(1, 16))

    footer_text = (
        "This document was generated locally for internal procurement, budgeting, "
        "comparison, and scenario-analysis purposes only."
        if is_baseline
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
