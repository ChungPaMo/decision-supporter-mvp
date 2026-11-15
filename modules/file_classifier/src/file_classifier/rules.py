"""규칙 기반 파일 유형 분류 (열 이름 중심).

판단 순서
    1. 시트마다 열 이름을 정규화하고, 첫 행이 열 이름이 아니면 샘플 행에서 열 이름 줄을 찾는다.
    2. 다섯 entity 각각에 대해 "핵심 열 조합"이 있는지와 "아는 열의 비율(coverage)"을 본다.
    3. 핵심 조합이 있고 coverage 가 기준 이상이며 2순위와 차이가 충분할 때만 추천한다. 아니면 보류한다.
    4. 파일 단위로 합친다. 표가 있는 시트가 모두 같은 entity 일 때만 추천한다.

점수는 규칙으로 계산한 참고값이며 확률이 아니다. 파일명은 판단에 쓰지 않는다(틀린 이름이 흔하다).
capacity / routing 은 분류 범주가 아니므로 보류한다. 판매·출고 내역과 가로로 펼친 월별 표는 보류하고
monthly_demand 로 변환할 수 있음을 안내한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MODULE_VERSION = "rules-0.2.0"
MIN_COVERAGE = 0.6      # 추천에 필요한 "아는 열" 비율
MASTER_MIN_COVERAGE = 0.7   # 제품·자재 마스터는 모르는 열이 섞이면 다른 자료일 가능성이 커서 더 엄격하게 본다
MIN_MARGIN = 0.15       # 1순위와 2순위 점수 차이
HEADER_SCAN_ROWS = 5    # 열 이름 줄을 찾을 때 살펴보는 샘플 행 수

_STRIP = re.compile(r"[\s\[\]\*:()（）_\-./]+")
_MONTH_HEADER = re.compile(r"^(\d{4}\d{2}|\d{4}년\d{1,2}월|\d{1,2}월|m\d{1,2})$")


def norm(text: str | None) -> str:
    """열 이름 비교용 정규화: 소문자, 공백·괄호·기호 제거, '(필수)' 표시 제거."""
    if not text:
        return ""
    return _STRIP.sub("", text.replace("(필수)", "").lower())


def _g(*names: str) -> frozenset[str]:
    return frozenset(norm(n) for n in names)


# 열 그룹: 이름 -> 정규화된 표기 집합
GROUPS: dict[str, frozenset[str]] = {
    # 제품
    "p_code": _g("제품코드", "제품번호", "완제품코드", "제품ID", "productid", "product_id", "product_code", "product_no", "sku", "sku_code"),
    "p_name": _g("제품명", "제품명칭", "제품이름", "완제품명", "product_name", "product_desc", "product_description"),
    "p_type": _g("제품유형", "제품구분", "제품분류", "product_type", "product_class", "product_category"),
    "p_extra": _g("브랜드", "브랜드명", "brand", "겹수", "ply", "롤수", "입수(롤)", "roll_count", "rolls", "출시일", "출시일자", "launch_date",
                  "단종일", "판매상태", "판매여부", "sales_status", "현재정가(원)", "정가", "list_price", "규격", "spec"),
    # 자재
    "m_code": _g("자재코드", "자재번호", "원자재코드", "부자재코드", "자재ID", "material_id", "material_code", "material_no"),
    "m_name": _g("자재명", "자재명칭", "원자재명", "material_name", "material_desc", "material_description"),
    "m_kind": _g("자재구분", "자재유형", "자재분류", "material_type", "material_class"),
    "m_extra": _g("주공급사코드", "주거래공급사", "주공급사", "main_supplier_id", "main_supplier", "최소주문량", "moq", "min_order_qty",
                  "구매단위", "purchase_unit", "사용여부", "사용유무", "is_active", "겹수", "평량(g/m2)", "원단폭(m)"),
    # 종류를 특정하지 못하는 품목 표기
    "g_code": _g("품목코드", "품번", "품목번호", "품목ID", "재고코드", "item_id", "item_code", "item_no", "코드", "code"),
    "g_name": _g("품목명", "품명", "명칭", "item_name", "item_desc", "description", "name"),
    "item_type": _g("품목구분", "품목유형", "item_type"),
    "unit": _g("단위", "기준단위", "기본단위", "수량단위", "단위명", "uom", "unit", "base_unit"),
    "safety": _g("안전재고", "안전재고량", "안전재고수량", "적정재고", "safety_stock", "safety_stock_qty", "min_stock"),
    # BOM
    "bom_code": _g("BOM코드", "BOM번호", "BOM", "bom_id", "bom_code"),
    "parent": _g("모품목코드", "모품목", "상위품목코드", "상위품목", "parent_item", "parent_id", "parent_code"),
    "comp": _g("구성품코드", "구성품", "자품목코드", "자품목", "하위품목코드", "하위품목", "component_id", "component_code", "component",
               "child_item"),
    "qty_per": _g("소요량", "원단위", "투입량", "단위소요량", "구성수량", "qty_per", "usage_qty", "quantity_per"),
    "bom_extra": _g("버전", "리비전", "version", "revision", "bom_version", "BOM버전", "상태", "승인상태", "status", "bom_status", "BOM상태", "활성",
                    "활성여부", "사용여부", "is_active", "적용여부", "active", "유효시작일", "기준생산량", "행번호", "항번", "구성품유형", "자재구분", "scrap",
                    "스크랩비율", "불량률",
                    "적용시작일", "valid_from", "유효종료일", "적용종료일", "valid_to", "기준수량", "기준량", "base_qty", "순번", "라인번호",
                    "line_no", "seq", "구성유형", "구성품구분", "component_type", "스크랩률", "손실률", "로스율", "scrap_rate"),
    # 재고
    "on_hand": _g("현재고", "현재고량", "실재고", "재고수량", "재고량", "보유재고", "보유수량", "on_hand_qty", "qty_on_hand", "on_hand", "stock_qty"),
    "allocated": _g("할당재고", "할당수량", "할당량", "예약재고", "allocated_qty", "allocated", "reserved_qty"),
    "available": _g("가용재고", "가용수량", "available_qty", "available"),
    "as_of": _g("기준일", "기준일자", "재고기준일", "조사일", "as_of_date", "stock_date", "as_of"),
    "warehouse": _g("창고", "보관창고", "창고코드", "warehouse", "location"),
    # 월 수요
    "period": _g("기준월", "수요월", "주문월", "년월", "연월", "기간", "period", "month", "year_month", "yyyymm", "target_month"),
    "d_qty": _g("수요량", "월수요", "월수요량", "월별수요량", "수요수량", "판매량", "demand_qty", "demand", "monthly_demand"),
    "g_qty": _g("수량", "qty", "quantity", "판매수량"),
    # 변환하면 월 수요가 되는 거래 내역의 단서
    "sale_date": _g("주문일자", "주문일", "출고일자", "출고일", "판매일자", "판매일", "매출일자", "order_date", "ship_date", "sales_date"),
    "ship_qty": _g("출고수량", "출하수량", "주문수량", "ship_qty", "order_qty", "sales_qty"),
    # 판단에서 빼는 열
    "neutral": _g("비고", "담당자", "등록일", "수정일", "No.", "remark", "remarks", "note", "memo"),
}
VOCAB = {
    "product": ("p_code", "p_name", "p_type", "p_extra", "g_code", "g_name", "item_type", "unit", "safety"),
    "material": ("m_code", "m_name", "m_kind", "m_extra", "g_code", "g_name", "item_type", "unit", "safety"),
    "bom": ("bom_code", "parent", "comp", "qty_per", "bom_extra", "p_code", "m_code", "m_kind", "g_code", "g_qty", "unit"),
    "inventory": ("on_hand", "allocated", "available", "as_of", "warehouse", "item_type", "g_code", "g_name", "p_code", "m_code", "unit"),
    "monthly_demand": ("period", "d_qty", "g_qty", "p_code", "p_name", "g_code", "g_name", "unit"),
}
LABEL = {"product": "제품 마스터", "material": "자재 마스터", "bom": "BOM", "inventory": "재고", "monthly_demand": "월 수요"}
# 마스터 자료에는 없어야 하는 열 (있으면 거래·집계 자료다)
FACT_GROUPS = ("period", "d_qty", "on_hand", "comp", "qty_per", "as_of", "sale_date", "ship_qty", "bom_code", "parent")
# 모르는 열 이름에 이런 말이 들어 있으면 기간·수량을 담은 자료로 보고 마스터로 추천하지 않는다
FACT_WORDS = ("월", "month", "yyyymm", "기간", "수요", "demand", "수량", "qty", "quantity", "재고", "stock", "일자", "날짜", "date", "소요", "금액",
              "단가", "amount", "price")


@dataclass
class SheetResult:
    name: str | None
    is_table: bool
    scores: dict[str, float] = field(default_factory=dict)      # entity -> 점수 (핵심 조합이 있는 entity 만)
    entity: str | None = None
    guidance: str | None = None                                 # 변환 안내 문구
    guidance_score: float = 0.0                                 # 월 수요 열 구성과의 일치도 (안내 후보용)
    reasons: list[str] = field(default_factory=list)


def _groups_of(cells: list[str | None]) -> tuple[list[str], dict[str, list[str]]]:
    """(비어 있지 않은 정규화 열 이름, 그룹 -> 원래 열 이름) 을 돌려준다."""
    names, found = [], {}
    for cell in cells:
        key = norm(cell)
        if not key:
            continue
        names.append(key)
        for group, aliases in GROUPS.items():
            if key in aliases:
                found.setdefault(group, []).append((cell or "").strip())
    return names, found


def _find_header(columns: list[str], sample_rows: list[list[str | None]]) -> tuple[list[str | None], bool]:
    """첫 행이 열 이름이면 그대로, 아니면 샘플 행에서 열 이름처럼 보이는 줄을 찾는다."""
    def looks_like_header(cells):
        names, found = _groups_of(cells)
        known = {n for n in names if any(n in GROUPS[g] for g in found)}
        return len(known) >= 2 and len(known) >= 0.5 * len(names)

    if looks_like_header(columns):
        return list(columns), False
    for row in sample_rows[:HEADER_SCAN_ROWS]:
        if looks_like_header(row):
            return list(row), True
    return list(columns), False


def _core(entity: str, has) -> bool:
    """entity 를 특정하는 핵심 열 조합이 있는가."""
    if entity == "product":
        specific = has("p_code") + has("p_name") + has("p_type")
        master = (specific >= 2 or (has("p_type") and (has("g_code") or has("g_name"))) or (has("p_code") and has("g_name"))
                  or (has("p_name") and has("g_code")))
        return master and not any(has(g) for g in FACT_GROUPS) and not has("fact_word")
    if entity == "material":
        master = ((has("m_code") and (has("m_name") or has("g_name") or has("m_kind"))) or (has("m_kind") and (has("g_code") or has("g_name")))
                  or (has("m_name") and has("g_code")))
        return master and not any(has(g) for g in FACT_GROUPS) and not has("fact_word")
    if entity == "bom":
        if has("comp") and (has("qty_per") or has("bom_code") or has("p_code") or has("parent")):
            return True
        # 구성품을 '자재코드'로 적은 BOM: BOM 코드나 모품목이 함께 있어야 BOM 으로 본다
        return has("m_code") and (has("bom_code") or has("parent")) and (has("qty_per") or has("g_qty"))
    if entity == "inventory":
        return has("on_hand") and (has("g_code") or has("p_code") or has("m_code"))
    if entity == "monthly_demand":
        return has("period") and ((has("d_qty") and (has("p_code") or has("g_code"))) or (has("g_qty") and has("p_code")))
    return False


def classify_sheet(name: str | None, columns: list[str], sample_rows: list[list[str | None]]) -> SheetResult:
    header, recovered = _find_header(columns, sample_rows)
    names, found = _groups_of(header)
    judged = [n for n in names if n not in GROUPS["neutral"]]
    result = SheetResult(name=name, is_table=len(judged) >= 2)
    if not result.is_table:
        result.reasons.append("열 이름이 없거나 한 개뿐이라 표로 보지 않았습니다.")
        return result
    if recovered:
        result.reasons.append("첫 행이 열 이름이 아니어서 샘플 행에서 열 이름 줄을 찾았습니다.")

    known_any = {n for n in judged for aliases in GROUPS.values() if n in aliases}
    fact_word = any(word in n for n in judged if n not in known_any for word in FACT_WORDS)

    def has(group: str) -> bool:
        return fact_word if group == "fact_word" else group in found

    for entity, vocab in VOCAB.items():
        if not _core(entity, has):
            continue
        known = sum(1 for n in judged if any(n in GROUPS[g] for g in vocab))
        result.scores[entity] = round(known / len(judged), 3)

    ranked = sorted(result.scores.items(), key=lambda kv: -kv[1])
    if ranked:
        top, top_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        evidence = ", ".join(sorted({h for g in VOCAB[top] for h in found.get(g, []) if g not in ("unit", "g_name")})[:6])
        if top_score < (MASTER_MIN_COVERAGE if top in ("product", "material") else MIN_COVERAGE):
            result.reasons.append(f"{LABEL[top]}의 핵심 열({evidence})이 있지만 알 수 없는 열이 많습니다(아는 열 {top_score:.0%}). 다른 종류의 보고서일 수 있습니다.")
        elif top_score - second < MIN_MARGIN:
            result.reasons.append(f"{LABEL[top]}와 {LABEL[ranked[1][0]]}의 열이 함께 있어 하나로 정하지 못했습니다.")
        else:
            result.entity = top
            result.reasons.append(f"{LABEL[top]}의 핵심 열이 있습니다: {evidence} (아는 열 {top_score:.0%}).")
            return result

    # 변환하면 월 수요가 되는 자료
    month_headers = [n for n in names if _MONTH_HEADER.match(n)]
    if (has("p_code") or has("g_code")) and len(month_headers) >= 3:
        result.guidance = "월이 가로로 펼쳐진 표입니다. 제품·월·수량의 세로 형태로 바꾸면 월 수요(monthly_demand)로 등록할 수 있습니다."
    elif has("p_code") and has("sale_date") and (has("g_qty") or has("ship_qty")):
        result.guidance = "주문·출고 건별 내역으로 보입니다. 제품·월 단위로 집계하면 월 수요(monthly_demand)로 등록할 수 있습니다."
    generic = sum(1 for n in judged if any(n in GROUPS[g] for g in ("g_code", "g_name", "unit", "safety", "item_type")))
    if result.guidance:
        demand_like = sum(1 for n in judged if n in month_headers or any(n in GROUPS[g] for g in VOCAB["monthly_demand"]))
        result.guidance_score = round(demand_like / len(judged), 3)
        result.reasons.append(result.guidance)
    elif not ranked:
        if has("g_code") and generic >= MIN_COVERAGE * len(judged):
            result.reasons.append("품목 코드·이름만 있어 제품인지 자재인지 열 이름으로는 구분할 수 없습니다.")
        else:
            result.reasons.append("다섯 가지 자료 유형(제품, 자재, BOM, 재고, 월 수요)의 핵심 열 조합을 찾지 못했습니다.")
    return result


def classify_sheets(sheets: list[tuple[str | None, list[str], list[list[str | None]]]]) -> dict:
    """파일 단위 결론. ClassificationOutput 에 넣을 값을 dict 로 돌려준다."""
    results = [classify_sheet(*s) for s in sheets]
    tables = [r for r in results if r.is_table]
    multi = len(sheets) > 1

    def label(r: SheetResult) -> str:
        return f"[{r.name}] " if multi and r.name else ""

    reasons = [label(r) + text for r in tables for text in r.reasons]
    scores: dict[str, float] = {}
    for r in tables:
        for entity, score in r.scores.items():
            scores[entity] = max(scores.get(entity, 0.0), score)
    for r in tables:
        if r.guidance:
            scores["monthly_demand"] = max(scores.get("monthly_demand", 0.0), r.guidance_score)
    candidates = [{"entity": e, "score": s, "reasons": [f"{LABEL[e]} 열 구성과의 일치도 {s:.0%} (확률 아님)"]}
                  for e, s in sorted(scores.items(), key=lambda kv: -kv[1])]

    if not tables:
        return {"recommended_entity": None, "candidates": [], "hold": True,
                "reasons": ["표로 볼 수 있는 시트가 없습니다(열 이름이 없거나 한 개뿐). 파일 유형을 직접 선택해 주세요."]}
    entities = {r.entity for r in tables}
    if len(entities) == 1 and None not in entities:
        entity = next(iter(entities))
        if multi and len(tables) > 1:
            reasons.insert(0, f"표가 있는 시트 {len(tables)}개가 모두 {LABEL[entity]}로 판단됩니다.")
        return {"recommended_entity": entity, "candidates": candidates, "hold": False, "reasons": reasons}
    if len(entities - {None}) > 1:
        kinds = ", ".join(f"{r.name or '시트'}={LABEL[r.entity]}" for r in tables if r.entity)
        reasons.insert(0, f"한 파일에 서로 다른 유형의 시트가 있습니다({kinds}). 유형별로 파일을 나눠 올려 주세요.")
    elif len(entities) > 1:
        reasons.insert(0, "일부 시트만 유형을 알 수 있어 파일 전체를 하나로 정하지 못했습니다.")
    return {"recommended_entity": None, "candidates": candidates, "hold": True, "reasons": reasons}
