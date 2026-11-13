"""Raster upload exercises real OCR, rather than embedded PDF text."""
import shutil

import fitz
import pytest

from app.core.config import settings


@pytest.mark.skipif(not shutil.which('tesseract'), reason='Tesseract binary required')
def test_scanned_invoice_upload_extract_review(client, sample_invoice_path, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ocr_processor_name', 'tesseract')
    image = tmp_path / 'synthetic-invoice.png'
    with fitz.open(sample_invoice_path) as pdf:
        pdf[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(image)
    with image.open('rb') as file:
        upload = client.post('/api/documents/upload', files={'file': (image.name, file, 'image/png')})
    assert upload.status_code == 200, upload.text
    doc_id = upload.json()['document_id']
    result = client.post(f'/api/documents/{doc_id}/extract')
    assert result.status_code == 200, result.text
    bill = client.get(f"/api/bills/{result.json()['bill_id']}").json()
    descriptions = ' '.join(item['description'] for item in bill['items']).lower()
    assert 'paper' in descriptions
    assert 'pen' in descriptions
    assert 'stapler' in descriptions
