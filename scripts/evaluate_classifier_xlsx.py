"""Audit the 200 tracked synthetic fixtures and score the actual read-only APIs."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import runpy
import sys

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'modules/file_classifier'
SAMPLES = MODULE / 'samples'
sys.path[:0] = [str(ROOT), str(ROOT / 'backend'), str(MODULE / 'src'), str(ROOT / 'modules/planning_engine')]

from app.config import Settings  # noqa: E402
from app.ingest.parsing import parse_file  # noqa: E402
from app.main import app  # noqa: E402
from file_classifier.doctype import VERSION, classify_workbook  # noqa: E402


# Independent column roles from the flat BOM generator, in physical column order.
# Block forms, transactions, stock reports and planning outputs need extraction
# and/or business context before they can represent a supported input entity.
FLAT_BOM_ROLES = ('product_id', 'component_id', 'qty_per')


def fold(value):
    return ''.join(str(value or '').lower().split())


def find_tables(ws, blocks):
    """Locate each independently known source table without using the backend parser or aliases."""
    locations = []
    rows = list(ws.values)
    after = 0
    for block in blocks:
        if block['kind'] != 'table':
            continue
        expected = tuple(map(fold, block['headers']))
        for idx in range(after, len(rows)):
            values = tuple(map(fold, rows[idx]))
            section = next((col for col in range(len(values) - len(expected) + 1)
                            if values[col:col + len(expected)] == expected), None)
            if section is not None:
                after = idx + 1 + len(block['rows'])
                locations.append({'row': idx + 1, 'first_col': section + 1, 'last_col': section + len(expected),
                                  'body_rows': len(block['rows']), 'grouped': bool(block['groups'])})
                break
        else:
            raise ValueError(f'Synthetic header not found on {ws.title}: {block["headers"]}')
    return locations


def sheet_audit(ws, selected, expected_title_rows):
    formulas = [cell for row in ws.iter_rows() for cell in row if cell.data_type == 'f']
    parsed_rows = {row.row: row for row in selected.rows} if selected else {}
    hidden = [dim for dim in ws.column_dimensions.values() if dim.hidden]
    hidden_columns = [i for dim in hidden for i in range(dim.min, dim.max + 1)]
    blank_rows = {number for number, row in enumerate(ws.values, 1) if all(value is None for value in row)}
    merged = [str(span) for span in ws.merged_cells.ranges]
    empty_formulas = sum(cell.column > len(row.cells) or row.cells[cell.column - 1].value is None
                         for cell in formulas if (row := parsed_rows.get(cell.row)) is not None)
    return {'name': ws.title, 'visibility': ws.sheet_state, 'source_rows': ws.max_row, 'source_width': ws.max_column,
            'parser_header_rows': selected.header_rows if selected else [], 'parser_width': selected.width if selected else 0,
            'parser_body_rows': len(parsed_rows), 'merged_ranges': sorted(merged), 'hidden_columns': hidden_columns,
            'hidden_columns_in_parser': [col for col in hidden_columns if selected and col <= selected.width],
            'formula_cells': len(formulas), 'body_formula_cells_parsed_empty': empty_formulas,
            'blank_rows': len(blank_rows), 'blank_rows_in_parser_body': len(blank_rows & parsed_rows.keys()),
            'title_rows': expected_title_rows,
            'title_used_as_header': bool(selected and set(selected.header_rows) & set(expected_title_rows))}


def request_json(client, path, name, content, data=None):
    response = client.post(path, files={'file': (name, content)}, data=data)
    if response.status_code != 200:
        raise ValueError(f'{name}: {path} returned {response.status_code} {response.text}')
    return response.json()


def mapping_probe(client, name, content, sheet, first_col, selection=None):
    form = {'entity': 'bom'}
    if selection is not None:
        form['table_selection'] = json.dumps(selection)
    result = request_json(client, '/ingest/mapping-suggestions', name, content, form)
    assert result['persisted'] is False and result['auto_approve'] is False
    if selection is not None:
        assert result['table_selection'] == selection and result['source_sha256'] == selection['source_sha256']
    reply = next(row for row in result['sheets'] if row['sheet'] == sheet)
    columns = {col['col']: col for col in reply['suggestions']}
    cases = []
    for position, expected in enumerate(FLAT_BOM_ROLES, first_col):
        col = columns.get(position, {})
        ranked = [candidate['target_field'] for candidate in col.get('suggestions', [])]
        cases.append({'col': position, 'parsed_header': col.get('source_column'), 'expected': expected, 'ranked': ranked})
    # Also count candidates surfaced on unrelated columns in the parsed sheet.
    false_candidates = [col['col'] for col in reply['suggestions']
                        if not first_col <= col['col'] < first_col + len(FLAT_BOM_ROLES) and col['suggestions']]
    return {'status': reply['status'], 'holds': reply['holds'], 'cases': cases, 'unlabeled_candidate_cols': false_candidates}


def mapping_scores(probes):
    cases = [case for probe in probes for case in probe['cases']]
    return {'files': len(probes), 'gold_columns': len(cases),
            'top1': sum(case['ranked'][:1] == [case['expected']] for case in cases),
            'top3': sum(case['expected'] in case['ranked'] for case in cases),
            'wrong_top1': sum(bool(case['ranked']) and case['ranked'][0] != case['expected'] for case in cases),
            'wrong_alternatives': sum(field != case['expected'] for case in cases for field in case['ranked'][1:]),
            'no_candidate': sum(not case['ranked'] for case in cases),
            'files_hold': sum(probe['status'] == 'HOLD' for probe in probes),
            'unlabeled_candidate_cols': sum(len(probe['unlabeled_candidate_cols']) for probe in probes)}


def check_workbook(client, label, blocks, data):
    name = label['file']
    parsed = parse_file(name, data)
    parsed_sheets = {sheet.name: sheet for sheet in parsed.sheets}
    wb = load_workbook(BytesIO(data))
    cached = load_workbook(BytesIO(data), data_only=True)
    try:
        ws = wb.active
        tables = find_tables(ws, blocks)
        metadata = {block['value'] for block in blocks if block['kind'] == 'title'}
        audited_sheets = [sheet_audit(sheet, parsed_sheets.get(sheet.title), [
            i for i, row in enumerate(sheet.values, 1) if any(isinstance(v, str) and v in metadata for v in row)
        ]) for sheet in wb.worksheets]
        document = classify_workbook([(sheet.title, [
            ['' if value is None else str(value) for value in row]
            for row in sheet.iter_rows(min_row=1, max_row=60, max_col=60, values_only=True)
        ]) for sheet in cached.worksheets[:20]])
        upload = request_json(client, '/classifications/file', name, data)
        sales = label['template'] == 'erp_kr_sales'
        flat_bom = label['template'] == 'bom_structure_table'
        disposition = ('BOM_PARTIAL_COLUMNS' if flat_bom else 'MONTHLY_SALES_POLICY_REVIEW' if sales else
                       'RESTRUCTURE_BOM' if label['category'] == 'BOM' else
                       'SPLIT_ITEM_MASTER' if label['template'] == 'erp_kr_item' else
                       'RECONCILE_STOCK_SNAPSHOT' if label['template'] in ('erp_stock_kurbel', 'erp_kr_stock') else 'UNSUPPORTED_DOCUMENT')
        result = {**label, 'sha256': parsed.sha256, 'active_sheet': ws.title, 'sheets': audited_sheets, 'gold_tables': tables,
                  'hidden_sheets_skipped': parsed.meta['hidden_sheets_skipped'], 'disposition': disposition,
                  'document_kind': document.category, 'document_hold': document.needs_review,
                  'upload_entity': upload['recommended_entity'], 'upload_hold_kind': upload['hold_kind']}
        first_table = tables[0]
        selection = {'source_sha256': parsed.sha256, 'sheet': ws.title, 'header_row': first_table['row'],
                     'data_start_row': first_table['row'] + 1, 'data_end_row': first_table['row'] + first_table['body_rows'],
                     'first_col': first_table['first_col'], 'last_col': first_table['last_col']}
        selected = client.post('/ingest/profile', files={'file': (name, data)},
                               data={'table_selection': json.dumps(selection)})
        if selected.status_code == 200:
            body = selected.json()
            assert body['source_sha256'] == parsed.sha256 and body['table_selection'] == selection
            assert len(body['sheets']) == 1 and body['sheets'][0]['sheet'] == ws.title
            columns = body['sheets'][0]['columns']
            assert [column['col'] for column in columns] == list(range(first_table['first_col'], first_table['last_col'] + 1))
            expected = next(block['headers'] for block in blocks if block['kind'] == 'table')
            assert [fold(column['column']) for column in columns] == list(map(fold, expected))
            result['selected_profile'] = {'header_verified': True, 'row_count': body['sheets'][0]['row_count']}
        else:
            code = selected.json()['detail']['code']
            assert selected.status_code == 422 and code in ('XLSX_HEADER_INVALID', 'XLSX_MERGED_RANGE'), selected.text
            result['selected_profile'] = {'header_verified': False, 'error': code}
        if flat_bom:
            table = tables[0]
            result['raw_mapping'] = mapping_probe(client, name, data, ws.title, table['first_col'])
            result['selected_mapping'] = mapping_probe(client, name, data, ws.title, table['first_col'], selection)
            # Isolate ranking from layout using the exact source rectangle (no rewritten headers,
            # inserted units or generated rows). This copy cannot be registered as a complete BOM.
            first = table['first_col']
            header = table['row']
            cleaned = Workbook()
            out = cleaned.active
            for row in cached[ws.title].iter_rows(min_row=header, max_row=header + table['body_rows'],
                                                 min_col=first, max_col=table['last_col'], values_only=True):
                out.append(row)
            buffer = BytesIO()
            cleaned.save(buffer)
            result['extracted_mapping'] = mapping_probe(client, name, buffer.getvalue(), out.title, 1)
        return result
    finally:
        wb.close()
        cached.close()


def summarize(rows):
    sheets = [sheet for row in rows for sheet in row['sheets']]
    metrics = {'files': len(rows), 'visible_sheets': sum(s['visibility'] == 'visible' for s in sheets),
               'multi_visible_files': sum(sum(s['visibility'] == 'visible' for s in r['sheets']) > 1 for r in rows),
               'hidden_sheets_skipped': sum(len(r['hidden_sheets_skipped']) for r in rows),
               'actual_active_first_header_found': sum(
                   any(r['gold_tables'][0]['row'] in s['parser_header_rows'] for s in r['sheets'] if s['name'] == r['active_sheet'])
                   for r in rows),
               'active_gold_header_after_row_1': sum(r['gold_tables'][0]['row'] > 1 for r in rows),
               'titles_used_as_header': sum(s['title_used_as_header'] for s in sheets),
               'two_row_parser_headers': sum(len(s['parser_header_rows']) == 2 for s in sheets),
               'blank_rows_in_parser_body': sum(s['blank_rows_in_parser_body'] for s in sheets),
               'merged_sheets': sum(bool(s['merged_ranges']) for s in sheets),
               'hidden_columns_in_parser': sum(len(s['hidden_columns_in_parser']) for s in sheets),
               'formula_cells': sum(s['formula_cells'] for s in sheets),
               'body_formula_cells_parsed_empty': sum(s['body_formula_cells_parsed_empty'] for s in sheets)}
    return {'parser': metrics, 'dispositions': dict(Counter(r['disposition'] for r in rows)),
            'document_rules': {'version': VERSION, **{split: {
                'files': sum(r['split'] == split for r in rows),
                'correct': sum(r['document_kind'] == r['category'] and not r['document_hold'] for r in rows if r['split'] == split),
                'hold': sum(r['document_hold'] for r in rows if r['split'] == split),
                'wrong': sum(r['document_kind'] != r['category'] and not r['document_hold'] for r in rows if r['split'] == split),
            } for split in sorted({r['split'] for r in rows})}},
            'upload_routes': dict(Counter(r['upload_entity'] or r['upload_hold_kind'] for r in rows)),
            'selected_profile': dict(Counter(r['selected_profile'].get('error', 'HEADER_VERIFIED') for r in rows)),
            'raw_mapping': mapping_scores([r['raw_mapping'] for r in rows if 'raw_mapping' in r]),
            'selected_mapping': mapping_scores([r['selected_mapping'] for r in rows if 'selected_mapping' in r]),
            'extracted_mapping': mapping_scores([r['extracted_mapping'] for r in rows if 'extracted_mapping' in r])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.artifacts/classifier_xlsx_evaluation.json')
    args = parser.parse_args()
    labels_bytes = (SAMPLES / 'labels.json').read_bytes()
    labels = json.loads(labels_bytes)['files']
    generated = runpy.run_path(str(SAMPLES / 'make_samples.py'))['build']()
    assert [{k: v for k, v in item.items() if k != '_write'} for item in generated] == labels
    inbox = SAMPLES / 'inbox'
    assert len(labels) == 200 and {file.name for file in inbox.glob('*.xlsx')} == {label['file'] for label in labels}
    inputs = [(label, record['_write'][0], (inbox / label['file']).read_bytes()) for label, record in zip(labels, generated)]
    # Keep persistence disabled. The API requests use the default master-free path.
    from unittest.mock import patch

    with patch('app.api.batches.get_settings', return_value=Settings(persistence='disabled')), TestClient(app) as client:
        rows = [check_workbook(client, label, blocks, data) for label, blocks, data in inputs]
    assert all(sha256((inbox / row['file']).read_bytes()).hexdigest() == row['sha256'] for row in rows)
    assert (SAMPLES / 'labels.json').read_bytes() == labels_bytes
    summary = summarize(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'labels_sha256': sha256(labels_bytes).hexdigest(), 'summary': summary, 'files': rows},
                                     ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
