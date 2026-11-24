"""Offline XLSX range and confirmed-memory experiments, independent of production."""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from io import BytesIO
from itertools import groupby
import json
from pathlib import Path
from time import perf_counter

from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries
from scipy.optimize import linear_sum_assignment

from app.ingest.mapping import norm_header
from app.ingest.parsing import parse_file
from app.ingest.xlsx_layout import workbook_layout
from evaluate_mapping_research import metrics, timing, write
from mapping_phase5_audit import compact
from mapping_phase5_data import OUT, read_panel
from mapping_phase5_local import prepare_local
from mapping_research_data import sha
from mapping_research_features import CATALOG, Lexicon
from mapping_research_phase3 import OUT as PHASE3


FOOTERS = {'합계', '총계', '소계', '비고', '주석', '작성', '결재', 'sum', 'total', 'subtotal', 'note', 'notes'}


@dataclass(frozen=True)
class Range:
    sheet: str
    header: int
    left: int
    right: int
    end: int
    depth: int = 1


def layout(workbook, *, styled=True):
    for sheet in workbook.worksheets:
        if sheet.sheet_state != 'visible':
            continue
        explicit = []
        for table in sheet.tables.values():
            left, header, right, end = range_boundaries(table.ref)
            if table.headerRowCount != 0 and end - bool(table.totalsRowCount) > header:
                explicit.append(Range(sheet.title, header, left, right, end - bool(table.totalsRowCount)))
        yield from explicit
        accepted_end = {}
        for line in range(1, sheet.max_row):
            if sheet.row_dimensions.get(line) and sheet.row_dimensions[line].hidden:
                continue
            cells = [sheet.cell(line, i) for i in range(1, sheet.max_column + 1)]
            nonempty = lambda cell: cell.value is not None and str(cell.value).strip() != ''
            for filled, values in groupby(cells, key=nonempty):
                row = list(values)
                if not filled or len(row) < 2 or any(cell.data_type != 's' for cell in row):
                    continue
                left, right = row[0].column, row[-1].column
                if any(accepted_end.get(col, 0) >= line for col in range(left, right + 1)):
                    continue
                if any(item.header <= line <= item.end and item.left <= right and item.right >= left for item in explicit):
                    continue
                signature = [norm_header(str(cell.value)) for cell in row]
                if len(set(signature)) != len(signature) or not all(signature):
                    continue
                mark = sum(bool(cell.font.bold or cell.fill.patternType or cell.border.bottom.style) for cell in row)
                body = []
                for after in range(line + 1, sheet.max_row + 1):
                    strip = [sheet.cell(after, c) for c in range(left, right + 1)]
                    labels = [norm_header(str(cell.value)) for cell in strip if nonempty(cell)]
                    if len(labels) < max(2, (len(row) + 1) // 2) or labels == signature:
                        break
                    first = str(next(cell.value for cell in strip if nonempty(cell))).strip().casefold()
                    if first.split(':', 1)[0].strip() in FOOTERS:
                        break
                    body.append(strip)
                if len(body) < 2:
                    continue
                change = sum(any(cell.data_type in ('n', 'd', 'b', 'f') and nonempty(cell) for cell in strip)
                             for strip in body[:3]) >= 1
                if not change and (not styled or mark < len(row) / 2):
                    continue
                depth = 1 + int(styled and any(span.max_row == line - 1 and left <= span.min_col
                               and span.max_col <= right and span.max_col > span.min_col for span in sheet.merged_cells.ranges))
                end = line + len(body)
                for col in range(left, right + 1):
                    accepted_end[col] = end
                yield Range(sheet.title, line, left, right, end, depth)


def iou(first, second):
    if first.sheet != second.sheet:
        return 0.0

    def area(item):
        return (item.right - item.left + 1) * (item.end - item.header + item.depth)

    overlap = max(0, min(first.right, second.right) - max(first.left, second.left) + 1) * max(
        0, min(first.end, second.end) - max(first.header - first.depth, second.header - second.depth))
    return overlap / (area(first) + area(second) - overlap)


def count_layout(gold, guesses):
    counts = Counter(gold=len(gold), candidates=len(guesses), matched=0, header=0, exact=0, grouped_correct=0,
                     grouped_gold=sum(item.depth > 1 for item in gold), matched_iou=0.0, documents_needing_review=0)
    if gold and guesses:
        costs = [[iou(expected, observed) for observed in guesses] for expected in gold]
        starts, ends = linear_sum_assignment(costs, maximize=True)
        for g, p in zip(starts, ends, strict=True):
            if costs[g][p] < .5:
                continue
            expected, observed = gold[g], guesses[p]
            counts['matched'] += 1
            counts['matched_iou'] += costs[g][p]
            counts['header'] += observed.header == expected.header
            counts['exact'] += observed == expected
            counts['grouped_correct'] += expected.depth > 1 and expected.depth == observed.depth and observed.header == expected.header
    counts['documents_needing_review'] += counts['exact'] != len(gold) or len(gold) != len(guesses)
    return counts


def ranges(args):
    from mapping_research_document import text, workbook_panel

    panel = workbook_panel(include_complex=True)
    methods, times, example_failures = defaultdict(Counter), defaultdict(list), []
    covered = 0
    for item in panel:
        truth = [Range(t['sheet'], t['row'], t['first_col'], t['last_col'], t['row'] + len(t['body']), len(t['headers']))
                 for t in item['tables']]
        if not truth:
            continue
        covered += 1
        expected_by_range = dict(zip(truth, item['tables'], strict=True))
        start = perf_counter()
        parsed = parse_file(item['label']['file'], item['data'])
        original = [Range(sheet.name, sheet.header_rows[-1], sheet.header[0].col, sheet.header[-1].col,
                          sheet.rows[-1].row, len(sheet.header_rows)) for sheet in parsed.sheets
                    if sheet.header_rows and sheet.header and sheet.rows]
        times['existing_parser'].append((perf_counter() - start) * 1000)
        methods['existing_parser'].update(count_layout(truth, original))
        for styled in (False, True):
            name = 'density_and_styles' if styled else 'density'
            start = perf_counter()
            with workbook_layout(item['data']) as book:
                candidates = list(layout(book, styled=styled))
            times[name].append((perf_counter() - start) * 1000)
            outcome = count_layout(truth, candidates)
            if styled:
                raw = load_workbook(BytesIO(item['data']), data_only=True, read_only=True)
                try:
                    for candidate in set(candidates) & expected_by_range.keys():
                        sheet = raw[candidate.sheet]
                        original = [[text(value) for value in row] for row in sheet.iter_rows(
                            min_row=candidate.header + 1, max_row=candidate.end, min_col=candidate.left,
                            max_col=candidate.right, values_only=True)]
                        expected = expected_by_range[candidate]['body']
                        for actual_row, expected_row in zip(original, expected, strict=True):
                            outcome['original_cells_compared'] += len(expected_row)
                            outcome['original_cells_equal'] += sum(a == b for a, b in zip(actual_row, expected_row, strict=True))
                finally:
                    raw.close()
            methods[name].update(outcome)
            if styled and outcome['documents_needing_review']:
                example_failures.append({'file': item['label']['file'], 'fixture_sha256': item['sha256'],
                                         'gold': len(truth), 'detected': len(candidates), 'exact': outcome['exact']})
    report = {}
    for name, values in methods.items():
        report[name] = {**values, 'precision_iou50': values['matched'] / max(1, values['candidates']),
            'recall_iou50': values['matched'] / max(1, values['gold']),
            'mean_iou_per_gold': values['matched_iou'] / max(1, values['gold']), 'timing': timing(times[name])}
    comparison = args.parse_cache
    prior = None
    if comparison.is_file():
        prior = {}
        for mode, records in json.loads(comparison.read_bytes())['data'].items():
            if isinstance(records, list):
                prior[mode] = {key: sum(row.get(key, 0) for row in records) for key in ('gold_ranges', 'unique_exact_ranges')}
    return {'panel_workbooks': len(panel), 'with_structure_gold': covered, 'methods': report,
            'parse_cache_historical_separate_panel': prior, 'failures': example_failures}


def layout_key(item):
    return sha(sorted((norm_header(h.display), obs.flags['leading_zero'] > 0, obs.flags['calendar_date'] > 0,
                       obs.flags['native_number'] > 0, obs.units) for h, obs in zip(item.headers, item.observations, strict=True)))


class ConfirmedMemory:
    def __init__(self):
        self.entries = {}

    def remember(self, dataset, schema, item, mappings, now, *, confirmed):
        if not confirmed or len(set(mappings.values())) != len(mappings) or set(mappings.values()) - set(item.fields):
            return
        self.entries[dataset, schema, item.entity, layout_key(item)] = (now, dict(mappings))

    def suggest(self, dataset, schema, item, now, *, verified=True, similar=False, max_age=180):
        key = dataset, schema, item.entity, layout_key(item)
        found = self.entries.get(key)
        headers = [norm_header(h.display) for h in item.headers]
        if found is None and similar:
            alternatives = [value for lookup, value in self.entries.items() if lookup[:3] == key[:3]
                            and len(set(value[1]) & set(headers)) / max(1, len(set(value[1]) | set(headers))) >= .70
                            and 0 <= now - value[0] <= max_age]
            found = alternatives[0] if len(alternatives) == 1 else None
        if found is None or not 0 <= now - found[0] <= max_age or (verified and item.route_suspect):
            return [None] * len(headers)
        _, mappings = found
        result = []
        for i, header in enumerate(headers):
            field = mappings.get(header)
            result.append(field if field and headers.count(header) == 1 and
                          (not verified or item.hard[i, item.fields.index(field)] is None) else None)
        return result


def memory(args):
    docs, digest = read_panel(args.output, 'development')
    lexicon = Lexicon(CATALOG)
    seen = set()
    state = ConfirmedMemory()
    first, repeat = [], []
    configs = {'exact': (False, False), 'similar': (False, True), 'validated_similar': (True, True)}
    results = {name: [] for name in configs}
    for tick, doc in enumerate(docs):
        item = prepare_local(doc, lexicon)
        key = doc['family']
        if key not in seen:
            seen.add(key)
            first.append(doc)
            good = {norm_header(col['header']): col['expected'] for col in doc['columns'] if col['expected']}
            state.remember(key, 'v1', item, good, tick, confirmed=True)
            continue
        repeat.append(doc)
        for name, (verified, similar) in configs.items():
            values = state.suggest(key, 'v1', item, tick, verified=verified, similar=similar)
            assert not any(state.suggest(key + '-other', 'v1', item, tick, similar=True))
            assert not any(state.suggest(key, 'v2', item, tick, similar=True))
            assert not any(state.suggest(key, 'v1', item, tick + 365, similar=True))
            results[name].append([{'prediction': field, 'top3': [field] if field else [], 'ranking': None} for field in values])
    return {'development_sha256': digest, 'first_user_confirmations': len(first), 'repeat_documents': len(repeat),
            'methods': {name: compact(metrics(repeat, predicted)) for name, predicted in results.items()}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('ranges', 'memory'))
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--parse-cache', type=Path, default=PHASE3 / 'documents' / 'layout.json')
    arguments = parser.parse_args()
    output = ranges(arguments) if arguments.action == 'ranges' else memory(arguments)
    write(arguments.output / f'{arguments.action}-results.json', output)
