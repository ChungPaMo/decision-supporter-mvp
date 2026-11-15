"""Actual scoped approved masters; resets only through the separately authorized DB fixture."""
from tests.test_db_dataset_e2e import api
from contracts.interfaces.ingestion import SalesTransformPolicy


def test_assistance_reads_only_selected_approved_masters_and_writes_no_batches(api):
    client, engine = api
    before = client.get('/batches', params={'dataset_id': 'CHUNGPAMO-2027'}).json()['total']
    data = b'product_id,period,demand_qty,unit\nCP-N3-3030,2026-01,1,EA\n'
    for dataset, expected in [('CHUNGPAMO-2027', 1), ('TISSUE-LEGACY', 0)]:
        reply = client.post('/ingest/profile', params={'dataset_id': dataset}, files={'file': ('d.csv', data)}, data={'use_approved_master': 'true'})
        assert reply.status_code == 200, reply.json()
        assert reply.json()['master_scope'] == dataset
        assert reply.json()['sheets'][0]['columns'][0]['known_product_match_ratio'] == expected
    assert client.get('/batches', params={'dataset_id': 'CHUNGPAMO-2027'}).json()['total'] == before


def test_transform_confirmation_and_approved_cross_reference_enforced_in_postgres(api):
    from tests.test_ingestion_assistance import sales
    client, engine = api
    data = sales([['2026-01-01', 'CP-N3-3030', '10', '팩', '정상', 'O1', 1]])
    before = client.get('/batches', params={'dataset_id': 'CHUNGPAMO-2027'}).json()['total']
    for dataset, expected in [('CHUNGPAMO-2027', 'POLICY_REVIEW_REQUIRED'), ('TISSUE-LEGACY', 'HAS_ERRORS')]:
        recipe = SalesTransformPolicy(dataset_id=dataset)
        reply = client.post('/ingest/transform-preview', params={'dataset_id': dataset}, files=[('files', ('raw.csv', data))],
                            data={'policy': recipe.model_dump_json(), 'use_approved_master': 'true'})
        assert reply.status_code == 200, reply.json()
        assert reply.json()['status'] == expected and reply.json()['persisted'] is False
    assert client.get('/batches', params={'dataset_id': 'CHUNGPAMO-2027'}).json()['total'] == before
