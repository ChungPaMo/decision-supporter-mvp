import hashlib
from io import BytesIO
import json

from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest

from app.main import app


def to_bytes(workbook):
    data = BytesIO()
    workbook.save(data)
    return data.getvalue()


def selection(content, **changes):
    return {'source_sha256': hashlib.sha256(content).hexdigest(), 'sheet': 'Actual',
            'header_row': 4, 'data_start_row': 6, 'data_end_row': 8,
            'first_col': 3, 'last_col': 6, **changes}


@pytest.fixture
def workbook():
    book = Workbook()
    cover = book.active
    cover.title = 'Cover'
    cover['A1'] = 'internal report'
    sheet = book.create_sheet('Actual')
    sheet['C1'] = 'Warehouse report'
    sheet.merge_cells('C1:F1')
    sheet.column_dimensions.group('D', 'E', hidden=True)
    headers = ['product_id', 'period', 'demand_qty', 'unit']
    for row, values in [(4, headers), (6, ['P1', '2027-01', 10, 'EA']),
                        (8, ['P2', '2027-02', '=1+2', 'EA']), (10, headers),
                        (11, ['P3', '2027-03', 300, 'EA'])]:
        for col, value in enumerate(values, 3):
            sheet.cell(row, col, value)
    sheet['A3'] = 'sample@example.test'
    book.create_sheet('Archive').sheet_state = 'veryHidden'
    return book


def test_layout_list_and_window_use_original_cells_without_formula_text(workbook):
    content = to_bytes(workbook)
    files = {'file': ('sample.xlsx', content)}
    with TestClient(app) as client:
        listing = client.post('/ingest/xlsx-layout', files=files).json()
        assert listing['window'] is None and listing['persisted'] is False
        assert [(s['name'], s['visibility']) for s in listing['sheets']] == [
            ('Cover', 'visible'), ('Actual', 'visible'), ('Archive', 'veryHidden')]
        response = client.post('/ingest/xlsx-layout', files=files, params={'sheet': 'Actual', 'row_limit': 8, 'col_limit': 6})
    assert response.status_code == 200, response.text
    assert response.json()['source_sha256'] == listing['source_sha256'] == hashlib.sha256(content).hexdigest()
    window = response.json()['window']
    assert window['hidden_columns'] == [4, 5] and window['merged_ranges'] == ['C1:F1']
    cells = {(c['row'], c['col']): (c['kind'], c['value']) for c in window['cells']}
    assert cells[1, 4] == ('merged', None)
    assert cells[4, 3] == ('text', 'product_id') and cells[8, 5] == ('formula', None)
    assert cells[7, 5] == ('empty', None) and cells[3, 1][1] == '[REDACTED]'


def test_selection_keeps_provenance_and_absolute_override_across_read_apis(workbook, monkeypatch):
    monkeypatch.setattr('app.api.ingest_assistance.get_service', lambda *_: pytest.fail('unexpected persistence'))
    other = workbook.create_sheet('Other')
    other.append(['product_id', 'period', 'demand_qty', 'unit'])
    other.append(['P9', '2027-03', 901, 'EA'])
    content = to_bytes(workbook)
    files = {'file': ('sample.xlsx', content)}
    chosen = selection(content)
    data = {'table_selection': json.dumps(chosen)}
    with TestClient(app) as client:
        original = client.post('/classifications/file', files=files).json()
        classified = client.post('/classifications/file', files=files, data=data).json()
        combined = client.post('/ingest/classified-mapping', files=files, data=data).json()
        mapped = client.post('/ingest/mapping-suggestions', files=files,
                             data={**data, 'column_overrides': '{"demand_qty":"E"}'}).json()
        profiled = client.post('/ingest/profile', files=files, data=data).json()
        second = selection(content, header_row=10, data_start_row=11, data_end_row=11)
        later = client.post('/ingest/profile', files=files,
                            data={'table_selection': json.dumps(second), 'include_samples': 'true'}).json()
        changed_sheet = selection(content, sheet='Other', header_row=1, data_start_row=2, data_end_row=2, first_col=1, last_col=4)
        other_result = client.post('/ingest/profile', files=files,
                                   data={'table_selection': json.dumps(changed_sheet), 'include_samples': 'true'}).json()
    assert original['hold'] and 'table_selection' not in original
    assert classified['recommended_entity'] == 'monthly_demand' and classified['table_selection'] == chosen
    assert combined['classification']['table_selection'] == chosen and combined['mapping']['table_selection'] == chosen
    assert not combined['persisted'] and not combined['auto_approve']
    assert mapped['table_selection'] == chosen and mapped['source_sha256'] == chosen['source_sha256']
    sheet = mapped['sheets'][0]
    assert sheet['existing_mapping']['demand_qty'] == 5 and [item['col'] for item in sheet['suggestions']] == [3, 4, 5, 6]
    assert profiled['sheets'][0]['row_count'] == 2 and profiled['sheets'][0]['columns'][2]['empty_count'] == 1
    assert later['table_selection'] == second and later['source_sha256'] == chosen['source_sha256']
    assert later['sheets'][0]['columns'][2]['example_values'] == [{'value': '300', 'count': 1}]
    assert other_result['table_selection'] == changed_sheet and other_result['source_sha256'] == chosen['source_sha256']
    assert other_result['sheets'][0]['columns'][2]['example_values'] == [{'value': '901', 'count': 1}]


@pytest.mark.parametrize(('changes', 'status', 'code'), [
    ({'sheet': 'actual'}, 422, 'XLSX_SHEET_INVALID'),
    ({'sheet': 'Archive'}, 422, 'XLSX_SHEET_INVALID'),
    ({'sheet': None}, 422, 'XLSX_RANGE_INVALID'),
    ({'source_sha256': 'a'*64}, 409, 'XLSX_SOURCE_CHANGED'),
    ({'header_row': 1}, 422, 'XLSX_MERGED_RANGE'),
    ({'data_end_row': 12}, 422, 'XLSX_RANGE_INVALID'),
    ({'data_end_row': 4}, 422, 'XLSX_RANGE_INVALID'),
    ({'data_start_row': 7, 'data_end_row': 7}, 422, 'XLSX_RANGE_INVALID'),
])
def test_bad_selection_has_explicit_error(workbook, changes, status, code):
    content = to_bytes(workbook)
    with TestClient(app) as client:
        response = client.post('/classifications/file', files={'file': ('sample.xlsx', content)},
                               data={'table_selection': json.dumps(selection(content, **changes))})
    assert response.status_code == status and response.json()['detail']['code'] == code


def test_duplicate_headers_are_rejected_and_missing_required_columns_still_hold(workbook):
    content = to_bytes(workbook)
    with TestClient(app) as client:
        only_product = selection(content, last_col=3)
        result = client.post('/ingest/mapping-suggestions', files={'file': ('sample.xlsx', content)},
                             data={'table_selection': json.dumps(only_product)}).json()['sheets'][0]
        assert result['status'] == 'HOLD' and 'REQUIRED_FIELD_MISSING:demand_qty' in result['holds']
        workbook['Actual']['D4'] = ' Product-ID '
        duplicate = to_bytes(workbook)
        response = client.post('/ingest/mapping-suggestions', files={'file': ('sample.xlsx', duplicate)},
                               data={'table_selection': json.dumps(selection(duplicate))})
        assert response.status_code == 422 and response.json()['detail']['code'] == 'XLSX_HEADER_INVALID'


def test_empty_or_repeated_form_range_cannot_fall_back_to_default(workbook):
    content = to_bytes(workbook)
    bounds = json.dumps(selection(content))
    with TestClient(app) as client:
        for parts in [[''], [bounds, bounds]]:
            files = [('file', ('sample.xlsx', content)), *[('table_selection', (None, part)) for part in parts]]
            result = client.post('/classifications/file', files=files)
            assert result.status_code == 422 and result.json()['detail']['code'] == 'XLSX_RANGE_INVALID'


def test_transform_keeps_original_row_column_and_selection_in_digest():
    book = Workbook()
    book.active.title = 'Cover'
    data_sheet = book.create_sheet('Actual')
    data_sheet['A1'] = 'Sales report'
    names = ['order_date', 'product_id', 'quantity', 'unit', 'status', 'order_id', 'line_id']
    for row, values in [(4, names), (6, ['2027-01-03', 'P1', 10, 'EA', '정상', 'O1', 1]),
                        (8, ['2027-01-03', 'P1', None, 'EA', '정상', 'O2', 1])]:
        for col, value in enumerate(values, 3):
            data_sheet.cell(row, col, value)
    content = to_bytes(book)
    first = selection(content, last_col=9, data_end_row=6)
    policy = {'dataset_id': 'TISSUE-LEGACY', 'user_confirmed': True,
              'columns': dict(zip(names, 'CDEFGHI'))}
    with TestClient(app) as client:
        def send(chosen, index='0'):
            return client.post('/ingest/transform-preview', files=[('files', ('report.xlsx', content))],
                               data={'policy': json.dumps(policy), 'table_selections': json.dumps({index: chosen})})
        good = send(first)
        assert good.status_code == 200, good.text
        response = good.json()
        assert response['status'] == 'TRANSFORMED_PREVIEW' and not response['persisted'] and not response['auto_approve']
        assert response['sources'][0]['table_selection'] == first
        assert response['records'][0]['source_locations'][0]['row'] == 6
        assert send({**first, 'data_end_row': 7}).json()['input_digest'] != response['input_digest']
        bad = send({**first, 'data_end_row': 8}).json()
        assert bad['status'] == 'HAS_ERRORS'
        assert bad['issues'][0]['location'] == {'source_index': 0, 'sheet': 'Actual', 'row': 8, 'col': 5}
        assert send(first, index='1').status_code == 422
