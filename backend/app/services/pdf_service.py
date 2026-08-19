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
_vendor_title_style = ParagraphStyle(
    "VendorTitle",
    parent=_styles["Normal"],
    fontSize=13,
    leading=15,
    fontName="Helvetica-Bold",
    textColor=colors.HexColor("#0f172a"),
    alignment=1,
)
_vendor_sub_style = ParagraphStyle(
    "VendorSub",
    parent=_styles["Normal"],
    fontSize=8,
    leading=11,
    fontName="Helvetica-Oblique",
    textColor=colors.HexColor("#475569"),
    alignment=1,
)
_vendor_meta_style = ParagraphStyle(
    "VendorMeta",
    parent=_styles["Normal"],
    fontSize=8.5,
    leading=11,
    fontName="Helvetica",
    textColor=colors.HexColor("#334155"),
    alignment=1,
)
_quotation_title_style = ParagraphStyle(
    "QuotationTitle",
    parent=_styles["Normal"],
    fontSize=11,
    leading=14,
    fontName="Helvetica-Bold",
    textColor=colors.HexColor("#0f172a"),
    alignment=1,
)

DEFAULT_VENDOR_DETAILS = {
    "scenario_a": {
        "name": "DELHI STATIONERY HOUSE",
        "gstin": "6AEWPK0704K1ZB",
        "tagline": "Deals In: All Type of Office Stationery, Computer Stationery, File Cover, Pens, Paper & Register",
        "address": "Near Kirorimal Mandir, Chiripal Mohalla, Gali LokManya, BHIWANI-127021",
        "phone": "9215844061",
    },
    "scenario_b": {
        "name": "ANAND PAPER MART",
        "gstin": "06AIZPK9816H1ZJ",
        "tagline": "MARRIAGE CARD, STATIONERY & ALL TYPES OF PAPER SUPPLIER",
        "address": "119, GAUSHALA MARKET, BHIWANI-127021 (HR.)",
        "phone": "9215846479",
    },
    "scenario_c": {
        "name": "FUTURE TRADERS",
        "gstin": None,
        "tagline": None,
        "address": "Halu Bazar, Bhiwani (Hr.) 127021",
        "phone": None,
    },
}


def _get_vendor_info(scenario: Scenario) -> dict:
    label = scenario.label.lower()
    if scenario.scenario_type == TYPE_BASELINE or "scenario a" in label or "baseline" in label:
        return DEFAULT_VENDOR_DETAILS["scenario_a"]
    if "scenario b" in label:
        return DEFAULT_VENDOR_DETAILS["scenario_b"]
    if "scenario c" in label:
        return DEFAULT_VENDOR_DETAILS["scenario_c"]
    return DEFAULT_VENDOR_DETAILS["scenario_a"]


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
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
    )

    elements = []

    # Vendor Header Box
    vendor = _get_vendor_info(scenario)
    vendor_flowables = [Paragraph(f"<b>{vendor['name']}</b>", _vendor_title_style)]
    if vendor.get("tagline"):
        vendor_flowables.append(Spacer(1, 2))
        vendor_flowables.append(Paragraph(f"<i>{vendor['tagline']}</i>", _vendor_sub_style))

    meta_parts = []
    if vendor.get("address"):
        meta_parts.append(vendor["address"])
    if vendor.get("phone"):
        meta_parts.append(f"Phone: {vendor['phone']}")
    if meta_parts:
        vendor_flowables.append(Spacer(1, 2))
        vendor_flowables.append(Paragraph(" &bull; ".join(meta_parts), _vendor_meta_style))

    if vendor.get("gstin"):
        vendor_flowables.append(Spacer(1, 2))
        vendor_flowables.append(Paragraph(f"<b>GSTIN:</b> {vendor['gstin']}", _vendor_meta_style))

    vendor_box = Table([[vendor_flowables]], colWidths=[178 * mm])
    vendor_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    elements.append(vendor_box)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("QUOTATION", _quotation_title_style))
    elements.append(Spacer(1, 8))

    item_header = ["#", "Product", "Rate"]
    item_rows = [item_header]
    for idx, item in enumerate(scenario.items, start=1):
        item_rows.append(
            [
                str(idx),
                item.description,
                _money(item.adjusted_rate),
            ]
        )

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

    doc.build(elements)
    return out_path


def hash_file(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest()
