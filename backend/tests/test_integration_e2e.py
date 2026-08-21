"""End-to-end integration test through the real HTTP API: upload -> extract
-> review/edit -> confirm -> generate scenarios -> generate PDFs.
TRD §15 integration test flow.
"""

from decimal import Decimal
from pathlib import Path

import fitz  # PyMuPDF, used only to verify PDF text content in this test
from fastapi.testclient import TestClient

from app.models.scenario import BASELINE_LABEL, SIMULATION_DISCLAIMER

# Known-good rate values from the fixture invoice, used to patch
# any OCR uncertainty before confirming.
EXPECTED_RATES = {
    "A4 Paper Rim 75 GSM": Decimal("240.00"),
    "Ball Pen Blue": Decimal("8.00"),
    "Stapler No. 10": Decimal("45.00"),
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
    assert len(bill["items"]) == 3

    # Patch any OCR-uncertain fields to known-good values before confirming,
    # exactly like a human reviewer would in FR-05.
    for item in bill["items"]:
        expected_rate = next((v for k, v in EXPECTED_RATES.items() if k in item["description"]), None)
        assert expected_rate is not None, f"unexpected item description: {item['description']}"
        resp = client.put(
            f"/api/bills/{bill_id}/items/{item['id']}",
            json={
                "rate": str(expected_rate),
            },
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["user_verified"] is True

    bill = client.get(f"/api/bills/{bill_id}").json()
    # 240.00 + 8.00 + 45.00 = 293.00
    assert Decimal(str(bill["grand_total"])) == Decimal("293.00")

    confirm = client.post(f"/api/bills/{bill_id}/confirm")
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["confirmed"] is True

    # Editing after confirmation must be rejected (bill is now immutable).
    locked = client.put(
        f"/api/bills/{bill_id}/items/{bill['items'][0]['id']}",
        json={"rate": "999.00"},
    )
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

    assert Decimal(str(baseline["grand_total"])) == Decimal("293.00")
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

    for (scenario_type, label), path in generated_paths.items():
        doc = fitz.open(path)
        try:
            text = "\n".join(page.get_text() for page in doc)
            assert label in text
            assert "Total" in text
            assert "Rs." in text
            if scenario_type == "BASELINE":
                assert BASELINE_LABEL in text
                # Extracted from the fixture invoice -- proves the letterhead
                # is real data, not a placeholder.
                assert "Delhi Stationery House" in text
            else:
                assert SIMULATION_DISCLAIMER in text
                # PRD compliance note / DATA.md §16 rule 10: a simulated
                # scenario must never carry the source vendor's identity.
                # (The word "GSTIN" legitimately appears in the compliance
                # footer itself -- "no ... GSTIN ... should be relied upon
                # as authentic" -- so check for the actual value, not the word.)
                assert "Delhi Stationery House" not in text
                assert "07ABCDE1234F" not in text
        finally:
            doc.close()


def test_simulated_scenarios_never_carry_vendor_identity(client: TestClient, sample_invoice_path: Path):
    """Regression guard for the anti-impersonation rule (PRD compliance
    note, DATA.md §16 rule 10): whatever vendor identity was extracted
    from the source document must appear only on the Baseline PDF, never
    on a SIMULATED scenario PDF."""
    document_id, bill_id = _upload_and_extract(client, sample_invoice_path)

    bill = client.get(f"/api/bills/{bill_id}").json()
    for item in bill["items"]:
        expected_rate = next((v for k, v in EXPECTED_RATES.items() if k in item["description"]), None)
        client.put(f"/api/bills/{bill_id}/items/{item['id']}", json={"rate": str(expected_rate)})

    assert client.post(f"/api/bills/{bill_id}/confirm").status_code == 200

    # The trimmed BillOut schema doesn't expose vendor fields via the API;
    # what actually matters is verified through the generated PDF content.
    scen_resp = client.post(
        f"/api/bills/{bill_id}/scenarios",
        json={"scenario_b_markup_percent": "10", "scenario_c_markup_percent": "20", "rounding": "none"},
    )
    scenario_ids = scen_resp.json()["scenario_ids"]
    scenarios = [client.get(f"/api/scenarios/{sid}").json() for sid in scenario_ids]

    for scenario in scenarios:
        pdf_resp = client.post(f"/api/scenarios/{scenario['id']}/pdf")
        path = Path(pdf_resp.json()["storage_path"])
        doc = fitz.open(path)
        try:
            text = "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
        if scenario["scenario_type"] != "BASELINE":
            assert "Delhi Stationery House" not in text
            assert "07ABCDE1234F" not in text  # GSTIN fragment must not leak
            assert "QUOTATION" not in text.upper() or SIMULATION_DISCLAIMER in text


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
    assert match["original_filename"] == sample_invoice_path.name
    assert match["status"] == "processed"


def test_delete_document(client: TestClient, sample_invoice_path: Path):
    document_id, _ = _upload_and_extract(client, sample_invoice_path)

    # Verify document exists in list
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    assert any(d["id"] == document_id for d in docs)

    # Delete document
    del_resp = client.delete(f"/api/documents/{document_id}")
    assert del_resp.status_code == 204

    # Verify document is removed from list
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    assert not any(d["id"] == document_id for d in docs)

    # Verify document detail returns 404
    get_resp = client.get(f"/api/documents/{document_id}")
    assert get_resp.status_code == 404


def test_delete_document_with_scenarios_and_files(client: TestClient, sample_invoice_path: Path):
    document_id, bill_id = _upload_and_extract(client, sample_invoice_path)

    # Confirm bill
    confirm = client.post(f"/api/bills/{bill_id}/confirm")
    assert confirm.status_code == 200

    # Generate scenarios
    scen_resp = client.post(
        f"/api/bills/{bill_id}/scenarios",
        json={"scenario_b_markup_percent": "10", "scenario_c_markup_percent": "20", "rounding": "nearest_1"},
    )
    assert scen_resp.status_code == 200
    scenario_ids = scen_resp.json()["scenario_ids"]

    # Generate PDFs
    for sid in scenario_ids:
        pdf_resp = client.post(f"/api/scenarios/{sid}/pdf")
        assert pdf_resp.status_code == 200

    # Verify files exist in API
    files_resp = client.get(f"/api/documents/{document_id}/files")
    assert files_resp.status_code == 200
    assert len(files_resp.json()["files"]) == 3

    # Delete the document
    del_resp = client.delete(f"/api/documents/{document_id}")
    assert del_resp.status_code == 204

    # Verify document is removed from list
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    assert not any(d["id"] == document_id for d in resp.json()["documents"])

    # Verify document detail returns 404
    get_resp = client.get(f"/api/documents/{document_id}")
    assert get_resp.status_code == 404

    # Verify files query returns 404
    files_after = client.get(f"/api/documents/{document_id}/files")
    assert files_after.status_code == 404


