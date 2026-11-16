"""Real classifier + existing mapper + sales preview, with persistence forbidden."""
import hashlib

import pytest
from fastapi.testclient import TestClient
from app.main import app
from contracts.interfaces.ingestion import SalesTransformPolicy


@pytest.mark.parametrize('header,entity', [
    ('product_id,product_name,base_unit', 'product'),
    ('material_id,material_name,base_unit', 'material'),
    ('product_id,period,demand_qty,unit', 'monthly_demand'),
])
def test_recommended_entity_reaches_existing_mapping(header, entity):
    data = (header + '\n').encode()
    body = TestClient(app).post('/ingest/classified-mapping', files={'file': ('p.csv', data)}).json()
    assert body['classification']['hold'] is False
    assert body['selected_entity'] == body['mapping']['entity'] == entity
    assert body['selection_method'] == 'CLASSIFIER_RECOMMENDATION'
    assert body['source_sha256'] == body['mapping']['source_sha256'] == hashlib.sha256(data).hexdigest()
    assert body['persisted'] is False and body['auto_approve'] is False


def test_hold_needs_manual_entity_and_overrides_do_not_silently_choose_it():
    client = TestClient(app)
    file = {'file': ('a.csv', b'code,name,unit\nP,Synthetic,EA\n')}
    body = client.post('/ingest/classified-mapping', files=file).json()
    assert body['classification']['hold'] and body['mapping'] is None
    assert body['next_action'] == 'SELECT_ENTITY_OR_TRANSFORM'
    response = client.post('/ingest/classified-mapping', files=file,
        data={'entity': 'product', 'column_overrides': '{"product_id":"A","product_name":"B","base_unit":"C"}'})
    assert response.status_code == 200
    assert response.json()['selection_method'] == 'USER_SELECTION'
    assert response.json()['mapping']['sheets'][0]['existing_mapping']['product_id'] == 1
    assert client.post('/ingest/classified-mapping', files=file,
        data={'column_overrides': '{"product_id":"A"}'}).status_code == 422


def test_sales_hold_connects_to_explicit_transform_policy_without_persistence():
    data = '주문일자,제품코드,수량,단위,구분,주문번호,행번호\n2026-01-01,P1,2,팩,정상,O1,1\n'.encode()
    client = TestClient(app)
    response = client.post('/ingest/classified-mapping', files={'file': ('s.csv', data)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['classification']['hold'] and body['mapping'] is None
    assert body['transform_preview_url'] == '/ingest/transform-preview'
    response = client.post(body['transform_preview_url'], files=[('files', ('s.csv', data))],
        data={'policy': SalesTransformPolicy(dataset_id='TISSUE-LEGACY', user_confirmed=True).model_dump_json()})
    assert response.status_code == 200
    assert response.json()['records'][0]['demand_qty'] == '2'
    assert response.json()['persisted'] is False


def test_capacity_routing_stay_hold_and_invalid_metadata_is_rejected():
    client = TestClient(app)
    response = client.post('/ingest/classified-mapping', files={'file': ('r.csv',
        b'routing_id,product_id,resource_id,run_time\nR,P,M,1\n')})
    assert response.status_code == 200 and response.json()['classification']['hold']
    assert client.post('/ingest/classified-mapping', files={'file': ('p.csv', b'a,b\n1,2\n')},
        data={'sample_row_limit': 21}).status_code == 422
