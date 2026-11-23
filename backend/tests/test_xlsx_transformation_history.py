"""Selected XLSX history through TestClient and the existing transactional test repository."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json

from fastapi import Depends
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
import pytest

from app.api.batches import get_service
from app.api.datasets import dataset_context
from app.api.ingest_history import get_history_service
from app.batches.service import BatchService
from app.ingest.history import TransformationService
from app.ingest.transformation import digest
from app.main import app
from tests.test_ingestion_history import DATASET, HistoryMemoryRepository, policy, sales


PARAMS = {'dataset_id': DATASET}
PREVIEW = '/ingest/transform-preview'
HISTORY = '/ingest/transformations'


def selected_workbook():
    book = Workbook()
    book.active.title = 'Cover'
    book.active['A1'] = 'Synthetic sales report'
    headers = list(policy().columns.model_dump().values())
    january = ['2027-01-03', 'P1', 10, 'EA', '정상', 'J1', 1]
    for name, values in [('January', january), ('February', ['2027-02-01', 'P1', 20, 'EA', '정상', 'F1', 1]),
                         ('Copy', january), ('Archive', january), ('Duplicate', january)]:
        sheet = book.create_sheet(name)
        sheet['C1'] = 'Title'
        sheet.merge_cells('C1:I1')
        for row, data in [(4, headers), (6, values)]:
            for col, value in enumerate(data, 3):
                sheet.cell(row, col, value)
    for row, data in [(8, ['2027-01-04', 'P1', 4, 'EA', '정상', 'J2', 1]),
                      (10, ['2027-01-05', 'P1', None, 'EA', '정상', 'J3', 1])]:
        for col, value in enumerate(data, 3):
            book['January'].cell(row, col, value)
    book['Duplicate']['D4'] = headers[0]
    book['Archive'].sheet_state = 'hidden'
    stream = BytesIO()
    book.save(stream)
    return [('sales.xlsx', stream.getvalue())]


def bounds(files, **updates):
    return {'source_sha256': hashlib.sha256(files[0][1]).hexdigest(), 'sheet': 'January',
            'header_row': 4, 'data_start_row': 6, 'data_end_row': 6, 'first_col': 3, 'last_col': 9, **updates}


@pytest.fixture
def api(monkeypatch):
    repos = {DATASET: HistoryMemoryRepository(), 'TISSUE-LEGACY': HistoryMemoryRepository('TISSUE-LEGACY')}

    def history(dataset_id: str = Depends(dataset_context)):
        return TransformationService(repos[dataset_id])

    def batches(dataset_id: str = Depends(dataset_context)):
        return BatchService(repos[dataset_id])

    monkeypatch.setitem(app.dependency_overrides, get_history_service, history)
    monkeypatch.setitem(app.dependency_overrides, get_service, batches)
    with TestClient(app) as client:
        yield client, repos[DATASET]


def post(client, path, files, data):
    return client.post(path, params=PARAMS, files=[('files', file) for file in files], data=data)


def prepare(client, files, chosen):
    form = {'policy': policy().model_dump_json(), 'table_selection': json.dumps(chosen)}
    preview = post(client, PREVIEW, files, form)
    assert preview.status_code == 200, preview.text
    return preview.json(), {**form, 'expected_result_digest': preview.json()['result_digest'],
                           'created_by': 'TEST-REVIEWER', 'source_note': 'Synthetic XLSX range'}


def test_selected_preview_save_replay_revalidate_approve_and_idempotency(api):
    client, repo = api
    files = selected_workbook()
    chosen = bounds(files, data_end_row=8)
    preview, form = prepare(client, files, chosen)
    assert preview['status'] == 'TRANSFORMED_PREVIEW' and preview['persisted'] is False
    assert 'XLSX_TABLE_SELECTION_PREVIEW_ONLY' not in preview['warnings']
    selected = preview['sources'][0]
    assert selected['table_selection'] == chosen and selected['resolved_columns']['quantity'] == 5
    assert selected['resolved_columns']['order_date'] == 3 and selected['resolved_columns']['line_id'] == 9
    locations = preview['records'][0]['source_locations']
    assert [(loc['sheet'], loc['row']) for loc in locations] == [('January', 6), ('January', 8)]
    assert preview['records'][0]['demand_qty'] == '14' and preview['counts']['source_rows'] == 2
    # A singular preview and equivalent indexed submission identify the same input.
    indexed = {key: value for key, value in form.items() if key != 'table_selection'}
    indexed['table_selections'] = json.dumps({'0': chosen})
    saved = post(client, HISTORY, files, indexed)
    assert saved.status_code == 201, saved.text
    result = saved.json()
    path = HISTORY + '/' + result['transformation_id']
    batch_path = '/batches/' + result['batch_id']
    assert result['persisted'] and not result['auto_approve'] and result['batch_status'] == 'READY_FOR_APPROVAL'
    assert result['input_digest'] == preview['input_digest'] and result['preview']['sources'] == preview['sources']
    assert result['preview']['persisted'] is False
    assert client.get(path, params=PARAMS).json()['preview']['records'][0]['source_locations'] == locations
    assert client.get(path).status_code == 404 and client.get(batch_path).status_code == 404
    assert client.get('/demand/monthly', params=PARAMS).json()['total'] == 0
    assert next(iter(repo.state.transformation_sources.values())) == files
    evidence = deepcopy(repo.state.transformations)
    retry = post(client, HISTORY, files, {**form, 'created_by': 'SECOND-REVIEWER'})
    assert retry.status_code == 200 and retry.json()['transformation_id'] == result['transformation_id']
    assert retry.json()['created_by'] == 'TEST-REVIEWER'

    batch = client.get(batch_path, params=PARAMS).json()
    revalidate = {'expected_version': batch['version'], 'column_overrides': {}, 'default_unit': None, 'sheet': None}
    rejected = client.post(batch_path + '/revalidate', params=PARAMS, json={**revalidate, 'sheet': 'January'})
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'TRANSFORM_BLOCKED'
    refreshed = client.post(batch_path + '/revalidate', params=PARAMS, json=revalidate)
    assert refreshed.status_code == 200 and refreshed.json()['version'] == batch['version'] + 1
    def approve(content_digest):
        return client.post(batch_path + '/approve', params=PARAMS, json={
            'approved_by': 'TEST-REVIEWER', 'expected_result_digest': content_digest})
    assert approve(result['result_digest']).json()['detail']['code'] == 'RESULT_CHANGED'
    assert approve(refreshed.json()['result_digest']).status_code == 200
    assert client.get(path, params=PARAMS).json()['batch_status'] == 'APPROVED'
    assert repo.state.transformations == evidence and next(iter(repo.state.transformation_sources.values())) == files
    assert client.get('/demand/monthly', params=PARAMS).json()['total'] == 1
    assert approve(refreshed.json()['result_digest']).status_code == 409


def test_separate_sheets_and_ranges_have_distinct_inputs_but_canonical_duplicates_are_blocked(api):
    client, repo = api
    files = selected_workbook()
    results = []
    for chosen in [bounds(files), bounds(files, data_end_row=8), bounds(files, sheet='February')]:
        _, form = prepare(client, files, chosen)
        new = post(client, HISTORY, files, form)
        assert new.status_code == 201, new.text
        results.append(new.json())
    assert len({row['input_digest'] for row in results}) == 3 and len(repo.state.batches) == 3
    assert {row['preview']['sources'][0]['sha256'] for row in results} == {bounds(files)['source_sha256']}
    duplicate, form = prepare(client, files, bounds(files, sheet='Copy'))
    assert duplicate['input_digest'] not in {row['input_digest'] for row in results}
    rejected = post(client, HISTORY, files, form)
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'DUPLICATE_UPLOAD'
    assert len(repo.state.batches) == len(repo.state.transformations) == 3


def test_mixed_csv_and_xlsx_index_preserves_each_file_path_and_coordinates(api):
    client, _ = api
    workbook = selected_workbook()
    files = [*sales(1), *workbook]
    fields = {'policy': policy().model_dump_json(), 'table_selections': json.dumps({'1': bounds(workbook)})}
    preview = post(client, PREVIEW, files, fields).json()
    result = post(client, HISTORY, files, {**fields, 'expected_result_digest': preview['result_digest'],
                                         'created_by': 'TEST-REVIEWER', 'source_note': 'Synthetic mixed sources'})
    assert result.status_code == 201, result.text
    detail = client.get(HISTORY + '/' + result.json()['transformation_id'], params=PARAMS).json()['preview']
    assert 'table_selection' not in detail['sources'][0] and 'resolved_columns' not in detail['sources'][0]
    assert detail['sources'][1]['table_selection'] == bounds(workbook)
    assert [(loc['source_index'], loc['sheet'], loc['row']) for record in detail['records']
            for loc in record['source_locations']] == [(0, '', 2), (1, 'January', 6)]


@pytest.mark.parametrize(('change', 'status', 'code'), [
    ({'data_end_row': 8}, 409, 'RESULT_CHANGED'),
    ({'sheet': 'February'}, 409, 'RESULT_CHANGED'),
    ({'source_sha256': '0'*64}, 409, 'XLSX_SOURCE_CHANGED'),
    ({'data_end_row': 25}, 422, 'XLSX_RANGE_INVALID'),
    ({'sheet': 'Archive'}, 422, 'XLSX_SHEET_INVALID'),
    ({'header_row': 1}, 422, 'XLSX_MERGED_RANGE'),
    ({'sheet': 'Duplicate'}, 422, 'XLSX_HEADER_INVALID'),
    ({'last_col': 8}, 422, 'TRANSFORM_MAPPING_HOLD'),
])
def test_save_rejects_changed_or_invalid_selection_without_staging(api, change, status, code):
    client, repo = api
    files = selected_workbook()
    _, form = prepare(client, files, bounds(files))
    response = post(client, HISTORY, files, {**form, 'table_selection': json.dumps(bounds(files, **change))})
    assert response.status_code == status and response.json()['detail']['code'] == code
    assert not repo.state.batches and not repo.state.files and not repo.state.transformations


def test_form_ambiguity_and_unconfirmed_or_errored_preview_cannot_stage(api):
    client, repo = api
    files = selected_workbook()
    preview, form = prepare(client, files, bounds(files, data_end_row=10))
    assert preview['status'] == 'HAS_ERRORS' and preview['issues'][0]['location']['col'] == 5
    blocked = post(client, HISTORY, files, form)
    assert blocked.status_code == 409 and blocked.json()['detail']['code'] == 'TRANSFORM_BLOCKED'
    for change in [{'table_selections': '{}'}, {'table_selection': ''}]:
        invalid = post(client, HISTORY, files, {**form, **change})
        assert invalid.status_code == 422 and invalid.json()['detail']['code'] == 'XLSX_RANGE_INVALID'
    singular_with_two_files = post(client, HISTORY, [*files, *sales(1)], form)
    assert singular_with_two_files.status_code == 422 and singular_with_two_files.json()['detail']['code'] == 'XLSX_RANGE_INVALID'
    unconfirmed = {**form, 'policy': policy().model_copy(update={'user_confirmed': False}).model_dump_json()}
    assert post(client, HISTORY, files, unconfirmed).json()['detail']['code'] == 'TRANSFORM_BLOCKED'
    assert client.get(HISTORY, params=PARAMS).json()['total'] == 0 and not repo.state.batches


def test_file_replaced_after_preview_is_rejected_even_when_selected_cells_are_unchanged(api):
    client, repo = api
    files = selected_workbook()
    _, form = prepare(client, files, bounds(files))
    workbook = load_workbook(BytesIO(files[0][1]))
    workbook['Cover']['A1'] = 'Different workbook bytes outside the selection'
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    changed = post(client, HISTORY, [('sales.xlsx', stream.getvalue())], form)
    assert changed.status_code == 409 and changed.json()['detail']['code'] == 'XLSX_SOURCE_CHANGED'
    assert not repo.state.batches


def test_staged_batch_with_unapproved_product_cannot_be_approved(api):
    client, repo = api
    repo.state.products.clear()
    files = selected_workbook()
    _, form = prepare(client, files, bounds(files))
    pending = post(client, HISTORY, files, form)
    assert pending.status_code == 201 and pending.json()['batch_status'] == 'HAS_ERRORS'
    path = '/batches/' + pending.json()['batch_id']
    batch = client.get(path, params=PARAMS).json()
    blocked = client.post(path + '/approve', params=PARAMS, json={
        'approved_by': 'TEST-REVIEWER', 'expected_result_digest': batch['result_digest']})
    assert blocked.status_code == 409 and blocked.json()['detail']['code'] == 'APPROVAL_BLOCKED_ERRORS'
    assert not repo.state.demand


def test_default_xlsx_save_retains_unselected_history_shape(api):
    client, _ = api
    workbook = Workbook()
    workbook.active.append(list(policy().columns.model_dump().values()))
    workbook.active.append(['2027-03-01', 'P1', 4, 'EA', '정상', 'M1', 1])
    stream = BytesIO()
    workbook.save(stream)
    files = [('standard.xlsx', stream.getvalue())]
    form = {'policy': policy().model_dump_json()}
    preview = post(client, PREVIEW, files, form).json()
    result = post(client, HISTORY, files, {**form, 'expected_result_digest': preview['result_digest'],
                                         'created_by': 'TEST-REVIEWER', 'source_note': 'Synthetic standard XLSX'})
    assert result.status_code == 201, result.text
    history = client.get(HISTORY + '/' + result.json()['transformation_id'], params=PARAMS).json()['preview']
    assert history['sources'] == preview['sources']
    assert set(history['sources'][0]) == {'source_index', 'filename', 'sha256', 'row_count'}


@pytest.mark.parametrize('key', ['table_selection', 'resolved_columns'])
def test_replay_detects_tampered_selection_or_columns_even_after_manifest_rehash(api, key):
    client, repo = api
    files = selected_workbook()
    _, form = prepare(client, files, bounds(files))
    detail = post(client, HISTORY, files, form).json()
    record = next(iter(repo.state.transformations.values()))
    source = record['manifest']['result']['sources'][0]
    source[key].update({'data_end_row': 7} if key == 'table_selection' else {'quantity': 4})
    record['manifest_digest'] = digest(record['manifest'])
    assert client.get(HISTORY + '/' + detail['transformation_id'], params=PARAMS).status_code == 500
    path = '/batches/' + detail['batch_id']
    batch = client.get(path, params=PARAMS).json()
    assert client.post(path + '/revalidate', params=PARAMS, json={'expected_version': batch['version']}).status_code == 500
    assert client.post(path + '/approve', params=PARAMS, json={
        'approved_by': 'TEST-REVIEWER', 'expected_result_digest': batch['result_digest']}).status_code == 500
    assert not repo.state.demand


def test_failed_insert_rolls_back_new_batch_and_keeps_approved_evidence(api):
    client, repo = api
    files = selected_workbook()
    _, form = prepare(client, files, bounds(files))
    first = post(client, HISTORY, files, form).json()
    path = '/batches/' + first['batch_id']
    batch = client.get(path, params=PARAMS).json()
    assert client.post(path + '/approve', params=PARAMS, json={
        'approved_by': 'TEST-REVIEWER', 'expected_result_digest': batch['result_digest']}).status_code == 200
    before = deepcopy(repo.state.__dict__)
    _, second = prepare(client, files, bounds(files, sheet='February'))
    repo.fail_history = True
    failed = post(client, HISTORY, files, second)
    assert failed.status_code == 500 and failed.json()['detail']['code'] == 'PERSISTENCE_ERROR'
    assert 'private' not in failed.text and repo.state.__dict__ == before
