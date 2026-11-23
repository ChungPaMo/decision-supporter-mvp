"""POST /classifications/documents: 여러 엑셀의 문서 종류를 한 번에 분류한다 (저장 없음, DB 없음)."""
import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app


def xlsx(rows):
    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_documents_are_sorted_without_storage_and_bad_files_do_not_fail_the_request():
    files = [
        ('files', ('a.xlsx', xlsx([['자재소요계획'], ['품목', '총소요량', '예정입고', '순소요량', '계획발주'], ['MR-1', 10, 0, 10, 10]]))),
        ('files', ('b.csv', '사번,성명,부서,직급\nE1,홍길동,총무,사원\n'.encode('utf-8'))),
        ('files', ('broken.xlsx', b'not an excel file')),
        ('files', ('memo.txt', b'hello')),
    ]
    with TestClient(app) as client:
        response = client.post('/classifications/documents', files=files)
    assert response.status_code == 200
    body = response.json()
    assert body['module_version'].startswith('doctype-') and '확인 필요' in body['categories']
    by_name = {r['file']: r for r in body['results']}
    assert by_name['a.xlsx']['category'] == 'MRP' and by_name['a.xlsx']['readable']
    assert by_name['b.csv']['category'] == '미분류'
    assert by_name['broken.xlsx']['category'] == '확인 필요' and not by_name['broken.xlsx']['readable']
    assert by_name['memo.txt']['category'] == '확인 필요' and '엑셀' in by_name['memo.txt']['reason']


def test_more_than_fifty_files_are_rejected():
    files = [('files', (f'{i}.csv', b'a,b\n1,2\n')) for i in range(51)]
    with TestClient(app) as client:
        response = client.post('/classifications/documents', files=files)
    assert response.status_code == 422 and response.json()['detail']['code'] == 'REQUEST_INVALID'
