"""Generates a synthetic printed invoice PDF fixture for pipeline testing.

Not part of the application itself -- a one-off content generator so the
extraction pipeline can be exercised against something resembling a real
scanned bill without needing an actual third-party document.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "printed_invoice_01.pdf"


def build() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(OUT_PATH), pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)

    elements = [
        Paragraph("Delhi Stationery House", styles["Title"]),
        Paragraph("123 Chandni Chowk, Delhi - 110006", styles["Normal"]),
        Paragraph("GSTIN: 07ABCDE1234F1Z5", styles["Normal"]),
        Spacer(1, 8),
        Paragraph("Invoice No: DSH/26-27/0896", styles["Normal"]),
        Paragraph("Date: 29/07/2026", styles["Normal"]),
        Spacer(1, 8),
        Paragraph("Bill To: G.M.S. Sec-13 HUDA", styles["Normal"]),
        Paragraph("Sector 13, HUDA, Gurugram", styles["Normal"]),
        Spacer(1, 12),
    ]

    # Header intentionally in a non-trivial column order to exercise FR-04.
    table_data = [
        ["S.No", "Description", "HSN/SAC", "Qty", "Unit", "Rate", "GST%", "Amount"],
        ["1", "A4 Paper Rim 75 GSM", "4802", "1", "RIM", "240.00", "18", "240.00"],
        ["2", "Ball Pen Blue", "9608", "10", "PCS", "8.00", "12", "80.00"],
        ["3", "Stapler No. 10", "8305", "2", "PCS", "45.00", "18", "90.00"],
    ]
    table = Table(table_data, colWidths=[12 * mm, 55 * mm, 20 * mm, 12 * mm, 15 * mm, 20 * mm, 15 * mm, 22 * mm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Grand Total: 479.00", styles["Normal"]))

    doc.build(elements)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    build()
