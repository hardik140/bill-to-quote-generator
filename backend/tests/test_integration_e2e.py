"""End-to-end integration test through the real HTTP API: upload -> extract
-> review/edit -> confirm -> generate scenarios -> generate PDFs.
TRD §15 integration test flow.
"""

from decimal import Decimal
from pathlib import Path

import fitz  # PyMuPDF, used only to verify PDF text content in this test
from fastapi.testclient import TestClient

from app.models.scenario import BASELINE_LABEL, SIMULATION_DISCLAIMER

# Known-good values from scripts/generate_fixture_invoice.py, used to patch
# over any OCR field the pipeline didn't confidently recover, so this test
# exercises confirm/scenario/PDF regardless of OCR variance on the table.
EXPECTED_ITEMS = {
    "A4 Paper Rim 75 GSM": {"quantity": Decimal("1"), "taxable_rate": Decimal("240.00"), "gst_rate": Decimal("18")},
    "Ball Pen Blue": {"quantity": Decimal("10"), "taxable_rate": Decimal("8.00"), "gst_rate": Decimal("12")},
    "Stapler No. 10": {"quantity": Decimal("2"), "taxable_rate": Decimal("45.00"), "gst_rate": Decimal("18")},
}


def _upload_and_extract(client: TestClient, pdf_path: Path) -> tuple[str, str]:
    with pdf_path.open("rb") as f:
        resp = client.post(
            "/api/documents/upload",
            files={"file": (pdf_path.name, f, "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    document_id = resp.json()["document_id"]

    resp = client.post(f"/api/documents/{document_id}/extract")
    assert resp.status_code == 200, resp.text
    bill_id = resp.json()["bill_id"]
    return document_id, bill_id


def test_full_flow_upload_to_pdf(client: TestClient, sample_invoice_path: Path):
    document_id, bill_id = _upload_and_extract(client, sample_invoice_path)

    bill = client.get(f"/api/bills/{bill_id}").json()
    assert bill["vendor_name"] == "Delhi Stationery House"
    assert bill["invoice_number"] == "DSH/26-27/0896"
    assert len(bill["items"]) == 3

    # Patch any OCR-uncertain fields to known-good values before confirming,
    # exactly like a human reviewer would in FR-05.
    for item in bill["items"]:
        expected = next((v for k, v in EXPECTED_ITEMS.items() if k in item["description"]), None)
        assert expected is not None, f"unexpected item description: {item['description']}"
        resp = client.put(
            f"/api/bills/{bill_id}/items/{item['id']}",
            json={
                "quantity": str(expected["quantity"]),
                "taxable_rate": str(expected["taxable_rate"]),
                "gst_rate": str(expected["gst_rate"]),
            },
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["user_verified"] is True

    bill = client.get(f"/api/bills/{bill_id}").json()
    # 240 + 80 + 90 = 410 subtotal; tax = 43.2 + 9.6 + 16.2 = 69.0
    assert Decimal(str(bill["subtotal"])) == Decimal("410.00")
    assert Decimal(str(bill["tax_total"])) == Decimal("69.00")
    assert Decimal(str(bill["grand_total"])) == Decimal("479.00")

    confirm = client.post(f"/api/bills/{bill_id}/confirm")
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["confirmed"] is True

    # Editing after confirmation must be rejected (bill is now immutable).
    locked = client.put(f"/api/bills/{bill_id}", json={"vendor_name": "Should Not Apply"})
    assert locked.status_code == 409

    scen_resp = client.post(
        f"/api/bills/{bill_id}/scenarios",
        json={"scenario_b_markup_percent": "10", "scenario_c_markup_percent": "20", "rounding": "nearest_1"},
    )
    assert scen_resp.status_code == 200, scen_resp.text
    scenario_ids = scen_resp.json()["scenario_ids"]
    assert len(scenario_ids) == 3

    scenarios = [client.get(f"/api/scenarios/{sid}").json() for sid in scenario_ids]
    baseline, scenario_b, scenario_c = scenarios

    assert baseline["grand_total"] == "479.00" or Decimal(str(baseline["grand_total"])) == Decimal("479.00")
    assert Decimal(str(scenario_b["grand_total"])) > Decimal(str(baseline["grand_total"]))
    assert Decimal(str(scenario_c["grand_total"])) > Decimal(str(scenario_b["grand_total"]))

    generated_paths = {}
    for scenario in scenarios:
        pdf_resp = client.post(f"/api/scenarios/{scenario['id']}/pdf")
        assert pdf_resp.status_code == 200, pdf_resp.text
        payload = pdf_resp.json()
        path = Path(payload["storage_path"])
        assert path.exists()
        generated_paths[scenario["scenario_type"], scenario["label"]] = path

    files_resp = client.get(f"/api/documents/{document_id}/files")
    assert files_resp.status_code == 200
    assert len(files_resp.json()["files"]) == 3

    for (_, label), path in generated_paths.items():
        doc = fitz.open(path)
        try:
            text = "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
        if "Scenario B" in label or "Scenario C" in label:
            assert SIMULATION_DISCLAIMER in text
        else:
            assert BASELINE_LABEL in text


def test_cannot_generate_scenarios_before_confirmation(client: TestClient, sample_invoice_path: Path):
    _, bill_id = _upload_and_extract(client, sample_invoice_path)

    resp = client.post(
        f"/api/bills/{bill_id}/scenarios",
        json={"scenario_b_markup_percent": "10", "scenario_c_markup_percent": "20", "rounding": "none"},
    )
    assert resp.status_code == 409


def test_document_list_reflects_history(client: TestClient, sample_invoice_path: Path):
    document_id, bill_id = _upload_and_extract(client, sample_invoice_path)

    resp = client.get("/api/documents")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    match = next(d for d in docs if d["id"] == document_id)
    assert match["vendor_name"] == "Delhi Stationery House"
    assert match["status"] == "processed"
