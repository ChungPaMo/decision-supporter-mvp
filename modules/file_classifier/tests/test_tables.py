"""표 위치 찾기(tables.py). 좌표는 1부터 시작하고 끝을 포함한다."""
import io

import pytest

from file_classifier.tables import find_tables, find_tables_in_xlsx


def ranges(rows, merged=None):
    return [(t.header_row, t.data_start_row, t.data_end_row, t.first_col, t.last_col) for t in find_tables(rows, 'S', merged)]


BODY = [['CP-1', '화장지', 10], ['CP-2', '키친타월', 20], ['CP-3', '미용티슈', 30]]


def test_header_on_the_first_row():
    assert ranges([['품목코드', '품목명', '수량'], *BODY]) == [(1, 2, 4, 1, 3)]


def test_title_approval_box_and_form_lines_above_the_table_are_skipped():
    rows = [
        [None, '주간 생산현황표', None, None, None, '결재', '담당', '과장'],     # 제목과 결재란 (아래가 비어 있다)
        [None] * 8,
        [None, '문서번호: 생산-261'],
        [None, '작성일자', '2026-12-10', '부서', '생산1팀'],                     # "항목 값" 줄
        [None] * 8,
        [None, '품목코드', '품목명', '수량'],
        *[[None, *r] for r in BODY],
    ]
    assert ranges(rows) == [(6, 7, 9, 2, 4)]


def test_form_line_directly_above_a_header_of_the_same_width():
    rows = [['작성일자', '2026-12-02', '부서', '총무팀', '작성자', '박준형'],
            ['근무일', '사번', '성명', '출근', '퇴근', '연장근로(h)'],
            ['2026-11-23', 'E7339', '정영호', '08:55', '18:05', 1],
            ['2026-12-04', 'E6829', '이수빈', '08:55', '18:05', 0]]
    assert ranges(rows) == [(2, 3, 4, 1, 6)]


def test_two_lines_of_key_value_pairs_above_the_header_are_not_a_table():
    rows = [[None, 'Material: MC', None, 'Plant: 1000', 'Usage: 1'],
            [None, 'Alternative: 01', None, 'Description: x', 'Base Qty: 1'],
            [None, 'Level', 'Item', 'Component', 'Qty', 'Un'],
            [None, '.1', '0010', 'MR-R2', 22.08, 'kg'],
            [None, '.1', '0020', 'MP-OUTBOX', 8.4, 'EA']]
    assert ranges(rows) == [(3, 4, 5, 2, 6)]


def test_header_with_period_numbers_and_repeated_blocks():
    block = lambda item: [['Item', item], ['Period', 1, 2, 3], ['Gross Requirements', 10, 20, 30], ['Net Requirements', 0, 5, 9], [None] * 4]
    assert ranges(block('MR-N3') + block('MR-N4')) == [(2, 3, 4, 1, 4), (7, 8, 9, 1, 4)]


def test_total_row_is_reported_but_left_out_of_the_data():
    found = find_tables([['품목코드', '품목명', '수량'], *BODY, ['합계', None, 60]], 'S')
    assert (found[0].data_end_row, found[0].total_row) == (4, 5)


def test_merged_group_header_is_not_the_header_row():
    rows = [['설비', '시간(분)', None, '효율', None],          # 묶음 머리글: B1:C1, D1:E1 이 병합돼 있다
            ['설비코드', '부하시간', '가동시간', '시간가동률', '양품률'],
            ['RW1', 480, 452, '94.2%', '97.1%'], ['RW2', 480, 442, '92.1%', '97.8%']]
    assert ranges(rows, merged={(1, 2), (1, 3), (1, 4), (1, 5)}) == [(2, 3, 4, 1, 5)]


@pytest.mark.parametrize('rows', [
    [],
    [['메모']],
    [['결재', '담당', '과장'], [None, None, None]],                    # 결재란만 있는 시트
    [['부서', '생산1팀'], ['작성자', '정대호']],                        # "항목 값" 두 줄
])
def test_sheets_without_a_table(rows):
    assert ranges(rows) == []


def test_xlsx_bytes_and_hidden_sheets():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Data'
    for row in [['주간 생산현황표'], [], ['품목코드', '품목명', '수량'], *BODY]:
        ws.append(row)
    hidden = wb.create_sheet('code')
    hidden.sheet_state = 'hidden'
    for row in [['A', 'B', 'C'], ['x', 'y', 'z'], ['x', 'y', 'z']]:
        hidden.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    found = find_tables_in_xlsx(buffer.getvalue())
    assert [(t.sheet, t.header_row, t.data_end_row, t.first_col, t.last_col) for t in found] == [('Data', 3, 6, 1, 3)]
