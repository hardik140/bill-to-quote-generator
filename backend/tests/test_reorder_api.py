def test_reorder_route_validates_permutation_and_locks(client, sample_invoice_path):
    with sample_invoice_path.open('rb') as file:
        document = client.post('/api/documents/upload', files={'file': ('reorder-test.pdf', file, 'application/pdf')}).json()
    result = client.post(f"/api/documents/{document['document_id']}/extract")
    assert result.status_code == 200, result.text
    bill_id = result.json()['bill_id']
    bill = client.get(f'/api/bills/{bill_id}').json()
    ids = [item['id'] for item in bill['items']]
    duplicate = client.put(f'/api/bills/{bill_id}/items/reorder', json={'item_ids_in_order': ids + ids[:1]})
    assert duplicate.status_code == 400
    reordered = client.put(f'/api/bills/{bill_id}/items/reorder', json={'item_ids_in_order': ids[::-1]})
    assert reordered.status_code == 200, reordered.text
    assert [item['id'] for item in reordered.json()] == ids[::-1]
    assert [item['serial_no'] for item in reordered.json()] == list(range(1, len(ids) + 1))
    refreshed = client.get(f'/api/bills/{bill_id}').json()
    assert refreshed['grand_total'] == bill['grand_total']
    assert client.post(f'/api/bills/{bill_id}/confirm').status_code == 200
    locked = client.put(f'/api/bills/{bill_id}/items/reorder', json={'item_ids_in_order': ids})
    assert locked.status_code == 409
