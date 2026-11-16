from fastapi.testclient import TestClient
import pytest
from app.main import app


def test_module_schema_is_generated_from_the_handoff_models():
    from export_contract_schema import OUT, build_modules
    assert (OUT.parent / 'schemas' / 'module_interfaces_draft.json').read_text(encoding='utf-8') == build_modules()


def test_module_metadata_reflects_owned_module_availability(monkeypatch):
    import file_classifier
    from engine import planning
    monkeypatch.setattr(file_classifier, 'AVAILABLE', True)
    monkeypatch.setattr(planning, 'AVAILABLE', True)
    with TestClient(app) as client: response = client.get('/integrations/modules')
    assert response.json()['file_classifier'] == 'IMPLEMENTED'
    assert response.json()['planning'] == 'IMPLEMENTED'
    assert response.json()['plan_persistence'] == 'ENGINE_GATED'
    assert response.json()['formal_plan_approval'] == 'DISABLED_AUTH_POLICY'


def test_real_classifier_holds_ambiguous_input_and_planning_remains_unimplemented():
    with TestClient(app) as client:
        result = client.post('/classifications', json={'filename': 'synthetic.csv', 'sha256': '0' * 64,
                             'sheets': [{'name': 'Sheet', 'columns': ['product'], 'sample_rows': [['TP-10R']]}]})
        assert result.status_code == 200
        assert result.json()['hold'] is True and result.json()['recommended_entity'] is None
        assert result.json()['reasons'] and 'batch_id' not in result.json()
        result = client.post('/plans', json={'forecast_execution_id': '00000000-0000-4000-8000-000000000001',
                             'product_ids': ['TP-10R'], 'target_month': '2027-01', 'as_of_date': '2026-12-31'})
        assert result.status_code == 501 and 'plans' not in result.json()


def test_unavailable_classifier_is_still_a_501(monkeypatch):
    import file_classifier
    monkeypatch.setattr(file_classifier, 'AVAILABLE', False)
    response = TestClient(app).post('/classifications/file', files={'file': ('p.csv', b'product_id,product_name,base_unit\nP,Synthetic,EA\n')})
    assert response.status_code == 501 and response.json()['detail']['code'] == 'MODULE_NOT_IMPLEMENTED'


def test_actual_classifier_connects_both_routes_without_creating_batches():
    client = TestClient(app)
    payload = {'filename': 'p.csv', 'sha256': '0' * 64, 'format': 'csv',
               'sheets': [{'name': None, 'columns': ['product_id', 'product_name', 'base_unit']}]}
    responses = [client.post('/classifications', json=payload), client.post('/classifications/file',
        files={'file': ('p.csv', b'product_id,product_name,base_unit\nP,Synthetic,EA\n')})]
    for response in responses:
        assert response.status_code == 200
        body = response.json()
        assert body['recommended_entity'] == 'product' and not body['hold']
        assert body['module_version'] and 'batch_id' not in body


def test_invalid_classifier_output_is_sanitized(monkeypatch):
    import file_classifier
    monkeypatch.setattr(file_classifier, 'classify', lambda request: {'private': 'credentials'})
    response = TestClient(app).post('/classifications/file', files={'file': ('p.csv', b'a,b\n1,2\n')})
    assert response.status_code == 500 and response.json()['detail']['code'] == 'MODULE_ERROR'
    assert 'credentials' not in response.text


@pytest.mark.parametrize('failure', [RuntimeError, ImportError])
def test_classification_handoff_validation_and_module_error_does_not_leak(monkeypatch, failure):
    import file_classifier
    def broken(request): raise failure('private input and credentials')
    monkeypatch.setattr(file_classifier, 'classify', broken)
    with TestClient(app) as client:
        result = client.post('/classifications', json={'filename': 'synthetic.csv', 'sha256': '0' * 64,
                             'sheets': [{'name': 'S', 'columns': ['id']}]})
        assert result.status_code == 500 and 'credentials' not in result.text
        assert client.post('/classifications', json={}).status_code == 422


def test_a_delivered_classifier_can_connect_without_bypassing_approval(monkeypatch):
    import file_classifier
    monkeypatch.setattr(file_classifier, 'classify', lambda request: {
        'recommended_entity': 'product', 'candidates': [{'entity': 'product', 'score': .9, 'reasons': ['synthetic test double']}],
        'hold': False, 'reasons': ['test double only'], 'module_version': 'TEST-ONLY',
    })
    with TestClient(app) as client:
        response = client.post('/classifications', json={'filename': 'synthetic.csv', 'sha256': '0' * 64,
                               'sheets': [{'name': 'S', 'columns': ['id']}]})
        assert response.status_code == 200
        assert response.json()['recommended_entity'] == 'product'
        assert 'approved' not in response.text.lower() and 'batch_id' not in response.text


def test_file_descriptor_omits_samples_without_consent_and_preserves_hold(monkeypatch):
    import file_classifier
    seen = []
    def classify(request):
        seen.append(request)
        return {'recommended_entity': None, 'candidates': [], 'hold': True, 'reasons': ['ambiguous test double'], 'module_version': 'TEST-ONLY'}
    monkeypatch.setattr(file_classifier, 'classify', classify)
    with TestClient(app) as client:
        for count in (0, 1):
            result = client.post('/classifications/file', files={'file': ('a.csv', b'product_id,qty\nTP-10R,10\n')}, data={'sample_row_limit': count})
            assert result.status_code == 200 and result.json()['hold'] is True
    assert seen[0].sheets[0].sample_rows == []
    assert seen[0].format == 'csv' and seen[0].sheets[0].name is None
    assert seen[1].sheets[0].sample_rows == [['TP-10R', '10']]
    assert seen[0].sha256 == seen[1].sha256
