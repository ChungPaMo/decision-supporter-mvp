"""문서 종류 분류(doctype) 규칙 시험. 엑셀을 읽지 않고 셀 격자만으로 확인한다."""
import pytest

from file_classifier.doctype import CATEGORIES, UNKNOWN, classify_workbook

CASES = {
    'BOM': [['모품목코드', '자품목코드', '소요량', '단위'], ['CP-N3-3030', 'MR-N3', 2.7, 'kg']],
    'MPS': [['계획주차', '제품코드', '제품명', '계획수량', '생산라인', '확정여부'], ['2027-W01', 'CP-N3-3030', '천연펄프 3겹', 8400, '1라인', '확정']],
    'MRP': [['자재코드', '자재명', '구분', 'W01', 'W02', 'W03'], ['MR-N3', '원단', '총소요량', 100, 200, 300], ['MR-N3', '원단', '순소요량', 0, 50, 80],
            ['MR-N3', '원단', '계획발주', 0, 5000, 0]],
    'RCCP': [['주요자원', '월', '필요시간(h)', '가용시간(h)', '부하율(%)'], ['롤 절단기', '2027-01', 150, 168, 89.3]],
    'CRP': [['작업장', '작업지시번호', '공정순번', '준비시간(h)', '가공시간(h)', '착수일'], ['WC-CUT', 'MO-270001', 20, 0.5, 6.0, '2027-01-05']],
    'MES': [['작업일자', '작업지시번호', '설비', '양품수량', '불량수량', '작업자'], ['2026-12-01', 'WO-260001', 'PK1', 4980, 20, '김가상']],
    'ERP': [['주문일자', '주문번호', '거래처명', '제품코드', '수량', '단가', '금액'], ['2026-12-01', 'SO-260001', '가상마트 본사', 'CP-N3-3030', 100, 9000, 900000]],
}


@pytest.mark.parametrize('category', CATEGORIES)
def test_each_category_is_recognised_from_headers_alone(category):
    verdict = classify_workbook([('Sheet1', CASES[category])])
    assert verdict.category == category and not verdict.needs_review and verdict.evidence


def test_title_and_offset_do_not_matter():
    grid = [['', '자재소요계획(MRP)'], [], ['', '자재코드', '기간', '총소요량', '예정입고', '순소요량']] + [['', 'MR-N3', 'W01', 100, 0, 100]]
    assert classify_workbook([('표지', [['', '㈜충파모제지']]), ('Data', grid)]).category == 'MRP'


def test_unrelated_documents_are_unclassified():
    verdict = classify_workbook([('S', [['사번', '성명', '부서', '직급', '입사일'], ['E1001', '김가상', '생산팀', '대리', '2020-03-02']])])
    assert verdict.category == UNKNOWN and not verdict.needs_review


def test_period_table_without_title_or_row_labels_needs_review():
    verdict = classify_workbook([('S', [['제품코드', '제품명', 'W01', 'W02', 'W03', 'W04'], ['CP-N3-3030', '천연펄프 3겹', 100, 200, 300, 400]])])
    assert verdict.category == UNKNOWN and verdict.needs_review


def test_rough_cut_and_detailed_capacity_are_told_apart():
    rccp = [['설비', '구분', '1월', '2월', '3월'], ['롤 절단기', '소요시간', 150, 160, 170], ['롤 절단기', '가용능력', 168, 168, 168], ['롤 절단기', '부하율(%)', 89, 95, 101]]
    crp = [['작업장', '구분', 'W01', 'W02', 'W03'], ['절단 작업장', '소요능력', 50, 60, 70], ['절단 작업장', '가용능력', 80, 80, 80], ['절단 작업장', '부하율(%)', 62, 75, 88]]
    assert classify_workbook([('S', rccp)]).category == 'RCCP'
    assert classify_workbook([('S', crp)]).category == 'CRP'


def test_acronyms_need_word_boundaries():
    verdict = classify_workbook([('S', [['Names', 'Times', 'Scrapbook', 'Bombay'], ['a', 'b', 'c', 'd']])])
    assert verdict.category == UNKNOWN


def test_empty_workbook_is_flagged_for_review():
    verdict = classify_workbook([('Sheet1', [])])
    assert verdict.category == UNKNOWN and verdict.needs_review


# 실제 문서 형태 (더미 v2 에서 처음에 놓쳤던 것들)
REAL_FORMS = {
    'BOM': [['Structure'], ['Upper-part-id', 'Lower-part-id', 'Quantity'], ['CP-N3-3030', 'MR-N3', 2.7]],
    'MPS': [['Product CP-N3-3030'], ['Safety stock: 20', 'WK 0', 'WK 1', 'WK 2', 'WK 3'], ['Demand forecast', '', 40, 35, 45],
            ['Firm Planned Order', '', 0, 20, 40], ['PAB', 55, 30, 20, 20], ['ATP', '', 20, 0, 20]],
    'MRP': [['Material', 'MR-N3', 'Plant', '1000', 'MRP type', 'PD'], ['Date', 'MRP element', 'MRP element data', 'Receipt/Reqmt', 'Available qty'],
            ['2026-12-28', 'Stock', '', '', 5000], ['2027-01-04', 'DepReq', '12345678', -800, 4200]],
    'RCCP': [['Master Schedule', 'MPS-2027Q1', 'Bill of Resources', 'BOR-STD'], ['Week Start Date', 'Department', 'Resource', 'Required Hours'],
             ['04-Jan', 'D1', 'R2', 240]],
    'CRP': [['Capacity Planning: Standard Overview'], ['Work center', '1320-01', 'Plant', '1000'],
            ['Week', 'Requirements', 'AvailCap.', 'CapLoad', 'RemAvailCap', 'Unit'], ['W 36/2026', 101.6, 80, '127 %', -21.6, 'H']],
    'MES': [['생산일지'], ['작성일자', '2026-12-01', '부서', '생산1팀'],
            ['작업시간', '품명', '규격', '수량', '공정명', '작업자', '품질공정검사', '검사내용', '결과'], ['08:00~17:00', '천연펄프 3겹', '3030', 4200, '포장', '김가상', '실시', '외관', '합격']],
    'ERP': [['Part', 'Physical inventory', 'Shop-floor stock', 'Reserved stock', 'Open order quantity', 'Reorder level', 'Safety stock'],
            ['MR-N3', 5000, 200, 300, 5000, 2000, 1000]],
}


@pytest.mark.parametrize('category', CATEGORIES)
def test_real_document_layouts_are_recognised(category):
    verdict = classify_workbook([('Report', REAL_FORMS[category])])
    assert verdict.category == category and not verdict.needs_review, verdict.scores


def test_capacity_plan_that_only_mentions_mps_is_not_an_mps():
    grid = [['기준', 'MPS 2027년 1분기'], ['설비', '구분', '1월', '2월', '3월'], ['롤 절단기', '소요공수', 150, 160, 170], ['롤 절단기', '보유공수', 168, 168, 168],
            ['롤 절단기', '부하율(%)', 89, 95, 101]]
    assert classify_workbook([('S', grid)]).category == 'RCCP'


# 의미 매칭과 규칙을 합치는 방식 (모델 없이 확인한다)
def _verdict(category, needs_review=False, score=5.0):
    from file_classifier.doctype import Verdict
    return Verdict(category, needs_review, '보통', score, reason='규칙 근거')


def test_semantic_result_fills_in_when_rules_cannot_decide():
    from file_classifier.doctype_embed import SemanticResult, combine
    shown, reason = combine(_verdict(UNKNOWN, score=0.0), SemanticResult('MES', {'MES': 2.4}, ['정품수량 ≈ 양품 수량']))
    assert shown == 'MES' and '정품수량' in reason


def test_disagreement_between_rules_and_semantic_matching_needs_review():
    from file_classifier.doctype_embed import REVIEW, SemanticResult, combine
    assert combine(_verdict('CRP'), SemanticResult('MES', {'MES': 3.0}, []))[0] == REVIEW
    assert combine(_verdict('CRP'), SemanticResult('CRP', {'CRP': 3.0}, []))[0] == 'CRP'
    assert combine(_verdict('CRP'), SemanticResult(UNKNOWN, {}, []))[0] == 'CRP'


def test_both_undecided_stays_undecided():
    from file_classifier.doctype_embed import REVIEW, SemanticResult, combine
    assert combine(_verdict(UNKNOWN, score=0.0), SemanticResult(UNKNOWN, {}, []))[0] == UNKNOWN
    assert combine(_verdict('MPS', needs_review=True), SemanticResult(None, {}, []))[0] == REVIEW
