from fastapi.testclient import TestClient
from app.main import app


def test_module_schema_is_generated_from_the_handoff_models():
    from export_contract_schema import OUT, build_modules
    assert (OUT.parent / 'schemas' / 'module_interfaces_draft.json').read_text(encoding='utf-8') == build_modules()


def test_unimplemented_modules_are_errors_and_never_forecast_or_plan_results():
    with TestClient(app) as client:
        result = client.post('/classifications', json={'filename': 'synthetic.csv', 'sha256': '0' * 64,
                             'sheets': [{'name': 'Sheet', 'columns': ['product'], 'sample_rows': [['TP-10R']]}]})
        assert result.status_code == 501 and result.json()['detail']['code'] == 'MODULE_NOT_IMPLEMENTED'
        result = client.post('/plans', json={'forecast_execution_id': '00000000-0000-4000-8000-000000000001',
                             'product_ids': ['TP-10R'], 'target_month': '2027-01', 'as_of_date': '2026-12-31'})
        assert result.status_code == 501 and 'plans' not in result.json()


def test_classification_handoff_validation_and_module_error_does_not_leak(monkeypatch):
    import file_classifier
    def broken(request): raise RuntimeError('private input and credentials')
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
