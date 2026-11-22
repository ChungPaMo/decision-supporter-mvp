"""팀 공식 합성 자료(CHUNGPAMO-2027)의 열 이름으로 분류 결과를 고정한다.

열 이름은 이희원 담당 생성기(modules/planning_engine/synthetic)의 출력 첫 줄을 그대로 옮긴 것이다.
백엔드 통합 시험(backend/tests/test_ingestion_api_e2e.py)이 쓰는 14개 파일과 같은 자료다.
생성기의 열 이름이 바뀌면 이 시험도 함께 고쳐야 한다.
"""
import pytest

from file_classifier.rules import classify_sheets

RECOMMENDED = {
    "01_products.csv": ("product", "제품코드,제품명,단위,제품유형,안전재고"),
    "02_materials.csv": ("material", "자재코드,자재명,단위,안전재고"),
    "05_monthly_demand.csv": ("monthly_demand", "product_id,period,demand_qty,unit"),
}

HELD = {
    "06_capacity_resources.csv": ("설비 능력(CAPA) 등록", "resource_id,resource_name,kind,time_basis,parallel_units"),
    "07_capacity_quantity_limits.csv": ("설비 능력(CAPA) 등록", "capacity_id,product_id,period,limit_qty,unit,accounting_point,operation_id"),
    "08_capacity_hours_budgets.csv": ("설비 능력(CAPA) 등록", "capacity_id,resource_id,period,regular_hours,overtime_hours_limit,unit,time_basis,availability_basis,calendar_ref"),
    "09_routing_steps.csv": ("라우팅 등록", "resource_id,reference_qty,quantity_unit,run_time,time_unit,time_basis,concurrent_units,setup_time,setup_policy_ref,alternative_group_ref,routing_id,routing_version,step_id,product_id,operation_id,predecessor_step_ids,valid_from,valid_to,resource_requirements"),
    "판매현황_2026.csv": ("월 수요(monthly_demand)", "주문일자,출고일자,주문번호,행번호,거래처코드,거래처명,채널,제품코드,제품명,수량,단위,단가,금액,구분,원주문번호"),
    "설비목록.csv": ("설비 능력(CAPA) 등록", "설비코드,설비명,구분,담당공정,대수·인원,도입연도,비고"),
    "월별가용시간계획.csv": ("설비 능력(CAPA) 등록", "적용월,설비코드,설비명,정규가용시간(h),잔업한도(h),산정기준,비고"),
    "월별생산한도.csv": ("설비 능력(CAPA) 등록", "관리번호,적용월,제품코드,제품명,최대생산수량,단위,집계기준,사유"),
}

# 다섯 유형과 비슷한 낱말이 섞여 있지만 추천하면 안 되는 거래·현황 자료
NEVER_RECOMMEND = {
    "재고수불부_2026.csv": "월,품목구분,품목코드,품목명,단위,기초재고,생산입고,구매입고,반품입고,판매출고,생산투입,반품폐기,기말재고",
    "생산실적_2026.csv": "생산일자,작업지시번호,제품코드,제품명,지시수량,양품수량,불량수량,단위,되감기설비,되감기시간(h),절단설비,절단시간(h),포장설비,포장시간(h),포장작업인시(h)",
    "자재투입내역_2026.csv": "투입일자,작업지시번호,제품코드,자재코드,자재명,투입수량,단위",
    "구매발주내역_2026.csv": "발주일,발주번호,공급사코드,공급사명,자재코드,자재명,발주수량,단위,단가,금액,납기예정일,입고수량,미입고수량,진행상태",
    "입고내역_2026.csv": "입고일,입고번호,발주번호,공급사코드,공급사명,자재코드,자재명,입고수량,단위,단가,금액,입고창고",
    "공정표.csv": "제품코드,제품명,공정순서,공정코드,공정명,설비코드,설비명,시간당처리량(팩),1000팩당작업인시,작업자코드,적용시작일",
}


def run(header: str) -> dict:
    return classify_sheets([(None, header.split(","), [])])


@pytest.mark.parametrize("name", RECOMMENDED)
def test_official_upload_files_are_recommended(name):
    entity, header = RECOMMENDED[name]
    out = run(header)
    assert out["recommended_entity"] == entity and out["hold"] is False


@pytest.mark.parametrize("name", HELD)
def test_official_files_outside_five_entities_are_held_with_route(name):
    route, header = HELD[name]
    out = run(header)
    assert out["recommended_entity"] is None and out["hold"] is True
    assert any(route in reason for reason in out["reasons"]), out["reasons"]


@pytest.mark.parametrize("name", NEVER_RECOMMEND)
def test_official_transaction_files_are_never_recommended(name):
    out = run(NEVER_RECOMMEND[name])
    assert out["recommended_entity"] is None and out["hold"] is True and out["reasons"]
