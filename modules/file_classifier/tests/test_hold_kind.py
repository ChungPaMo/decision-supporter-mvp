"""보류한 이유의 종류(hold_kind)를 모듈이 직접 돌려준다. 화면이 안내 문구를 고를 때 쓴다 (rules-0.4.0)."""
import pytest

from contracts.interfaces.modules import ClassificationInput
from file_classifier import classify
from file_classifier.rules import classify_sheets


def kind(columns, name="S"):
    return classify_sheets([(name, columns.split(","), [])])


@pytest.mark.parametrize("columns", [
    "주문일자,출고일자,주문번호,거래처코드,제품코드,제품명,수량,단위,단가,금액",       # 판매 내역 → 월 단위로 집계
    "제품코드,제품명,1월,2월,3월,4월,5월,6월",                                     # 월이 가로로 펼쳐진 표 → 세로로 변환
])
def test_data_that_becomes_monthly_demand_after_conversion_is_needs_transform(columns):
    out = kind(columns)
    assert out["hold"] and out["hold_kind"] == "NEEDS_TRANSFORM" and out["recommended_entity"] is None


@pytest.mark.parametrize("columns", [
    "resource_id,resource_name,kind,time_basis,parallel_units",
    "적용월,설비코드,설비명,정규가용시간(h),잔업한도(h),산정기준,비고",
    "routing_id,routing_version,step_id,product_id,operation_id,resource_id,run_time,time_unit",
])
def test_capacity_and_routing_are_other_route(columns):
    out = kind(columns)
    assert out["hold"] and out["hold_kind"] == "OTHER_ROUTE"


def test_item_list_that_could_be_product_or_material_is_ambiguous():
    out = kind("품목코드,품목명,단위")
    assert out["hold"] and out["hold_kind"] == "AMBIGUOUS"


def test_sheets_of_different_types_are_ambiguous():
    out = classify_sheets([("제품", "제품코드,제품명,단위,제품유형,안전재고".split(","), []),
                           ("자재", "자재코드,자재명,단위,안전재고".split(","), [])])
    assert out["hold"] and out["hold_kind"] == "AMBIGUOUS"


@pytest.mark.parametrize("sheets", [
    [("S", "사번,성명,부서,직급,입사일".split(","), [])],      # 다섯 유형과 무관한 표
    [("S", ["메모"], [])],                                    # 표가 아니다
])
def test_no_evidence_is_unknown(sheets):
    out = classify_sheets(sheets)
    assert out["hold"] and out["hold_kind"] == "UNKNOWN"


def test_recommendation_has_no_hold_kind_and_output_passes_the_contract():
    request = ClassificationInput(filename="a.csv", sha256="0" * 64, format="csv",
                                  sheets=[{"name": None, "columns": "제품코드,제품명,단위,제품유형,안전재고".split(","), "sample_rows": []}])
    out = classify(request)
    assert not out.hold and out.hold_kind is None and out.module_version == "rules-0.4.0"
    held = classify(request.model_copy(update={"sheets": [request.sheets[0].model_copy(update={"columns": "품목코드,품목명,단위".split(",")})]}))
    assert held.hold and held.hold_kind == "AMBIGUOUS"
