from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest

from app.main import app
from contracts.interfaces.modules import ClassificationOutput


EXAMPLES = Path(__file__).resolve().parents[2] / 'contracts/examples/tissue_capacity'
RESOURCE_HEADERS = ['resource_id', 'resource_name', 'kind', 'time_basis', 'parallel_units']


def classify(client, *sheets):
    response = client.post('/classifications', json={'filename': 'synthetic.xlsx', 'sha256': '0'*64, 'sheets': [
        {'name': name, 'columns': headers} for name, headers in sheets]})
    assert response.status_code == 200, response.text
    return ClassificationOutput.model_validate(response.json())


@pytest.mark.parametrize(('filename', 'entity', 'sections'), [
    ('capacity_upload.xlsx', 'capacity', {'resources', 'quantity_limits', 'hours_budgets'}),
    ('routing_upload.xlsx', 'routing', {'routing_steps'}),
])
def test_explicit_registration_route_for_existing_xlsx_templates(monkeypatch, filename, entity, sections):
    def forbidden(*args, **kwargs):
        pytest.fail('Classification and mapping recommendations must not load batch storage')

    monkeypatch.setattr('app.api.ingest_assistance.get_service', forbidden)
    data = (EXAMPLES / filename).read_bytes()
    with TestClient(app) as client:
        response = client.post('/ingest/classified-mapping', files={'file': (filename, data)})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload['mapping'] is None and payload['selected_entity'] is None
        assert payload['approval_required'] and not payload['persisted'] and not payload['auto_approve']
        result = ClassificationOutput.model_validate(payload['classification'])
        assert result.hold and result.hold_kind == 'OTHER_ROUTE' and result.recommended_entity is None
        assert result.registration_hint.entity == entity and set(result.registration_hint.sections) == sections


def test_mixed_or_incomplete_workbooks_never_get_exact_registration_hints():
    with TestClient(app) as client:
        mixed = classify(client, ('resources', RESOURCE_HEADERS), ('Product', ['product_id', 'product_name', 'base_unit']))
        assert mixed.hold_kind == 'AMBIGUOUS' and mixed.registration_hint is None
        for name, headers in [('resources', RESOURCE_HEADERS[:-1]), ('routing_steps', RESOURCE_HEADERS),
                              ('resources', [*RESOURCE_HEADERS, 'resource_id'])]:
            result = classify(client, (name, headers))
            assert result.registration_hint is None


def test_hold_codes_preserve_legacy_human_reasons():
    with TestClient(app) as client:
        cases = [
            ('NEEDS_TRANSFORM', ['제품코드', '주문일자', '수량']),
            ('AMBIGUOUS', ['품목코드', '품명', '단위']),
            ('UNKNOWN', ['일정', '작성자']),
        ]
        for expected, headers in cases:
            result = classify(client, ('Sheet', headers))
            assert result.hold and result.hold_kind == expected and result.reasons


def test_native_hold_code_takes_precedence_over_legacy_message(monkeypatch):
    monkeypatch.setattr('file_classifier.classify', lambda _: {
        'recommended_entity': None, 'candidates': [], 'hold': True, 'hold_kind': 'AMBIGUOUS',
        'reasons': ['Localized review message'], 'module_version': 'future-rules',
    })
    with TestClient(app) as client:
        result = classify(client, ('Sheet', ['one', 'two']))
    assert result.hold_kind == 'AMBIGUOUS' and result.reasons == ['Localized review message']


def test_title_cannot_turn_lower_registration_headers_into_a_route():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'resources'
    sheet.append(['CAPA internal report'])
    sheet.merge_cells('A1:E1')
    sheet.append([])
    sheet.append(RESOURCE_HEADERS)
    sheet.append(['R', 'Machine', 'EQUIPMENT', 'MACHINE_HOUR', '1'])
    data = BytesIO()
    workbook.save(data)
    with TestClient(app) as client:
        result = client.post('/classifications/file', files={'file': ('report.xlsx', data.getvalue())})
    assert result.status_code == 200
    assert result.json()['hold'] and result.json()['registration_hint'] is None


def test_numeric_bom_quantity_is_not_offered_as_a_unit():
    with TestClient(app) as client:
        response = client.post('/ingest/mapping-suggestions', data={'entity': 'bom'}, files={
            'file': ('partial.csv', b'Upper-part-id,Lower-part-id,Quantity,Unit\nP,M,2,EA\nP,N,4,kg\n'),
        })
    assert response.status_code == 200, response.text
    reply = response.json()
    sheet = reply['sheets'][0]
    quantity, unit = sheet['suggestions'][2:]
    assert [candidate['target_field'] for candidate in quantity['suggestions']] == ['qty_per']
    assert 'unit:NUMERIC_VALUES_ARE_NOT_UNITS' in quantity['unresolved_reasons']
    assert unit['suggestions'][0]['target_field'] == 'unit'
    assert sheet['status'] == 'HOLD' and not reply['auto_approve'] and not reply['persisted']
