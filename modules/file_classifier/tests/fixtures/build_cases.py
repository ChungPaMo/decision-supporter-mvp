"""파일 분류기 시험셋 생성기 (SYNTHETIC). 표준 라이브러리만 사용한다.

    python -X utf8 modules/file_classifier/tests/fixtures/build_cases.py

같은 SEED 면 항상 같은 결과가 나온다. 산출물:
    cases.json     분류기 입력(ClassificationInput payload)과 기대 결과
    manifest.csv   사례 목록 (사람이 훑어보는 용도)

가상 회사는 modules/planning_engine/synthetic 의 ㈜충파모제지 설정(제품·자재 코드 체계, 보고서 열 구성)을
참고했다. 실제 기업 자료가 아니며 회사·제품·수치는 모두 가정이다.

기대 결과 필드
    content          파일에 실제로 담긴 자료 종류 (설명용)
    expected_entity  올바른 추천 entity. 추천하면 안 되는 사례는 null
    must_hold        보류만 정답인 사례
    hold_ok          추천이 정답이지만 보류해도 오분류로 보지 않는 어려운 사례
    guidance_entity  보류하되 "변환하면 이 entity 가 된다"고 안내해야 하는 사례 (판매 주문 → monthly_demand)

정한 규칙 (2026-11-16)
    - capacity / routing 은 분류 범주에 넣지 않는다. 들어오면 보류한다.
    - 판매 주문 원장, 가로로 펼친 월별 표처럼 변환이 필요한 자료는 보류하고 monthly_demand 로 안내한다.
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import random

SEED = 20261116
HERE = pathlib.Path(__file__).resolve().parent
ENTITIES = ("product", "material", "bom", "inventory", "monthly_demand")

# ---------------------------------------------------------------------------
# 가상 회사 기준 자료
# ---------------------------------------------------------------------------
PRODUCTS = [(f"CP-{kind}{ply}-{length}{rolls}", f"{pulp} {ply}겹 {length}m {rolls}롤", str(safety))
            for kind, pulp in (("N", "천연펄프"), ("R", "재생펄프"))
            for ply in (2, 3, 4) for length, rolls, safety in ((30, 30, 1000), (27, 30, 800), (25, 24, 600), (30, 12, 300))]
MATERIALS = [("MR-N2", "천연펄프 2겹 원단 점보롤", "원단", "kg", "2000", "SUP-PULP-A"),
             ("MR-N3", "천연펄프 3겹 원단 점보롤", "원단", "kg", "3000", "SUP-PULP-A"),
             ("MR-N4", "천연펄프 4겹 원단 점보롤", "원단", "kg", "500", "SUP-PULP-B"),
             ("MR-R2", "재생펄프 2겹 원단 점보롤", "원단", "kg", "1500", "SUP-RECYCLE"),
             ("MR-R3", "재생펄프 3겹 원단 점보롤", "원단", "kg", "1200", "SUP-RECYCLE"),
             ("MR-R4", "재생펄프 4겹 원단 점보롤", "원단", "kg", "400", "SUP-RECYCLE"),
             ("MC-CORE", "지관(심지)", "부자재", "EA", "50000", "SUP-CORE"),
             ("MC-GLUE", "지관 접착제", "부자재", "kg", "200", "SUP-CORE"),
             ("MP-FILM30", "포장필름 30롤용", "포장재", "EA", "3000", "SUP-PACK"),
             ("MP-FILM24", "포장필름 24롤용", "포장재", "EA", "1000", "SUP-PACK"),
             ("MP-FILM12", "포장필름 12롤용", "포장재", "EA", "800", "SUP-PACK"),
             ("MP-GIFTBOX", "선물세트 박스", "포장재", "EA", "300", "SUP-PACK"),
             ("MP-OUTBOX4", "외박스 4입", "포장재", "EA", "500", "SUP-PACK"),
             ("MP-OUTBOX6", "외박스 6입", "포장재", "EA", "500", "SUP-PACK"),
             ("MP-OUTBOX8", "외박스 8입", "포장재", "EA", "300", "SUP-PACK"),
             ("MP-LABEL", "제품 라벨 스티커", "포장재", "EA", "20000", "SUP-PACK"),
             ("MP-TAPE", "박스 테이프", "포장재", "EA", "100", "SUP-PACK"),
             ("MP-PALLET", "목재 팔레트", "포장재", "EA", "50", "SUP-PACK"),
             ("MC-EMBOSS", "엠보 접착액", "부자재", "kg", "150", "SUP-CORE"),
             ("MC-PERFUME", "향료", "부자재", "kg", "30", "SUP-CORE"),
             ("MC-INK", "인쇄 잉크", "부자재", "kg", "40", "SUP-PACK"),
             ("MP-STRETCH", "스트레치 필름", "포장재", "EA", "60", "SUP-PACK")]
CUSTOMERS = [("CU-001", "가상마트 본사", "대형마트"), ("CU-002", "가상편의점", "편의점·슈퍼"), ("CU-003", "가상몰", "온라인"),
             ("CU-004", "가상도매상사", "대리점·도매"), ("CU-005", "가상호텔", "기업·업소")]
SUPPLIERS = [("SUP-PULP-A", "가상펄프상사"), ("SUP-PULP-B", "가상원지공업"), ("SUP-RECYCLE", "가상재생제지"),
             ("SUP-CORE", "가상지관산업"), ("SUP-PACK", "가상포장")]
RESOURCES = [("RW1", "되감기·엠보기 1호", "EQUIPMENT"), ("RW2", "되감기·엠보기 2호", "EQUIPMENT"), ("SAW1", "롤 절단기", "EQUIPMENT"),
             ("PK1", "포장기 1호", "EQUIPMENT"), ("PK2", "포장기 2호", "EQUIPMENT"), ("LB1", "포장 작업자", "LABOR_POOL")]
NAMES = ["김가상", "이모의", "박예시", "최샘플", "정테스트", "강더미", "조임시", "윤가정"]


def month(i: int) -> str:
    return f"{2025 + i // 12}-{i % 12 + 1:02d}"


def day(rng: random.Random, year: int = 2026) -> str:
    return f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


# ---------------------------------------------------------------------------
# 다섯 entity 의 열 정의: key -> (한글 표기들, 영문 표기들). 첫 번째가 표준 표기다.
# ---------------------------------------------------------------------------
COL = {
    "product_code": (["제품코드", "제품번호", "완제품코드", "제품 코드"], ["product_id", "product_code", "sku"]),
    "product_name": (["제품명", "제품명칭", "제품 이름"], ["product_name", "product_desc"]),
    "unit": (["단위", "기준단위", "UOM"], ["unit", "uom"]),
    "product_type": (["제품유형", "제품구분", "제품분류"], ["product_type", "product_class"]),
    "safety_stock": (["안전재고", "안전재고량", "적정재고"], ["safety_stock", "min_stock"]),
    "brand": (["브랜드", "브랜드명"], ["brand"]),
    "ply": (["겹수"], ["ply"]),
    "rolls": (["롤수", "입수(롤)"], ["roll_count"]),
    "launch": (["출시일", "출시일자"], ["launch_date"]),
    "sale_status": (["판매상태", "판매여부"], ["sales_status"]),
    "list_price": (["현재정가(원)", "정가"], ["list_price"]),
    "material_code": (["자재코드", "자재번호", "원자재코드", "자재 코드"], ["material_id", "material_code"]),
    "material_name": (["자재명", "자재명칭", "원자재명"], ["material_name", "material_desc"]),
    "material_kind": (["자재구분", "자재유형"], ["material_type"]),
    "main_supplier": (["주공급사코드", "주거래 공급사"], ["main_supplier_id"]),
    "moq": (["최소주문량", "MOQ"], ["min_order_qty"]),
    "use_yn": (["사용여부", "사용유무"], ["is_active"]),
    "bom_code": (["BOM코드", "BOM번호"], ["bom_id", "bom_code"]),
    "version": (["버전", "리비전"], ["version", "revision"]),
    "status": (["상태", "승인상태"], ["status"]),
    "active": (["활성", "적용여부"], ["active"]),
    "valid_from": (["유효시작일", "적용시작일"], ["valid_from"]),
    "valid_to": (["유효종료일", "적용종료일"], ["valid_to"]),
    "base_qty": (["기준수량", "기준량"], ["base_qty"]),
    "seq": (["순번", "라인번호"], ["line_no", "seq"]),
    "comp_type": (["구성유형", "구성품구분"], ["component_type"]),
    "comp_code": (["구성품코드", "자품목코드", "하위품목코드"], ["component_id", "component_code"]),
    "qty_per": (["소요량", "원단위", "투입량"], ["qty_per", "usage_qty"]),
    "scrap": (["스크랩률", "손실률", "로스율"], ["scrap_rate"]),
    "item_type": (["품목구분", "품목유형"], ["item_type"]),
    "item_code": (["품목코드", "품번", "품목번호"], ["item_id", "item_code"]),
    "as_of": (["기준일", "재고기준일", "조사일"], ["as_of_date", "stock_date"]),
    "on_hand": (["현재고", "현재고량", "실재고"], ["on_hand_qty", "qty_on_hand"]),
    "allocated": (["할당재고", "예약재고"], ["allocated_qty"]),
    "available": (["가용재고", "가용수량"], ["available_qty"]),
    "warehouse": (["창고", "보관창고"], ["warehouse"]),
    "period": (["기준월", "수요월", "년월"], ["period", "month"]),
    "demand_qty": (["수요량", "월수요", "수요수량"], ["demand_qty"]),
}


def rows_product(rng, n):
    out = []
    for code, name, safety in rng.sample(PRODUCTS, min(n, len(PRODUCTS))):
        ply, rolls = code.split("-")[1][1], code[-2:]
        out.append({"product_code": code, "product_name": name, "unit": rng.choice(["EA", "EA", "팩"]), "product_type": "완제품",
                    "safety_stock": safety, "brand": rng.choice(["충파모 순수", "충파모 데일리", "충파모 에코"]), "ply": ply, "rolls": rolls,
                    "launch": day(rng, rng.randint(2016, 2025)), "sale_status": rng.choice(["판매중", "판매중", "단종"]),
                    "list_price": str(rng.randrange(7900, 17000, 100))})
    return out


def rows_material(rng, n):
    return [{"material_code": c, "material_name": nm, "unit": u, "safety_stock": s, "material_kind": k, "main_supplier": sup,
             "moq": str(rng.choice([1000, 2000, 5000, 10000])), "use_yn": "Y"}
            for c, nm, k, u, s, sup in rng.sample(MATERIALS, min(n, len(MATERIALS)))]


def rows_bom(rng, n):
    out = []
    for code, _, _ in rng.sample(PRODUCTS, len(PRODUCTS)):
        kind, ply, rolls = code[3], code[4], code[-2:]
        film = {"30": "MP-FILM30", "24": "MP-FILM24", "12": "MP-FILM12"}[rolls]
        for seq, (comp, qty, unit) in enumerate([(f"MR-{kind}{ply}", f"{int(rolls) * 0.09:.2f}", "kg"), ("MC-CORE", rolls, "EA"), (film, "1", "EA")], 1):
            out.append({"bom_code": f"BOM-{code}", "product_code": code, "version": "V1", "status": "APPROVED", "active": "Y",
                        "valid_from": "2025-01-01", "valid_to": None, "base_qty": "1", "seq": str(seq), "comp_type": "MATERIAL",
                        "comp_code": comp, "qty_per": qty, "unit": unit, "scrap": rng.choice(["0", "0.02", "0.05"])})
            if len(out) == n:
                return out
    return out


def rows_inventory(rng, n):
    out, as_of = [], rng.choice(["2026-10-31", "2026-11-30", "2026-12-31"])
    prod_label, mat_label = rng.choice([("PRODUCT", "MATERIAL"), ("제품", "자재")])
    items = [(prod_label, c, "EA") for c, _, _ in PRODUCTS] + [(mat_label, m[0], m[3]) for m in MATERIALS]
    for item_type, code, unit in rng.sample(items, min(n, len(items))):
        on_hand = rng.randrange(0, 90000, 50)
        alloc = rng.choice([0, 0, on_hand // 10])
        out.append({"item_type": item_type, "item_code": code, "as_of": as_of, "on_hand": str(on_hand), "allocated": str(alloc),
                    "available": str(on_hand - alloc), "unit": unit, "warehouse": rng.choice(["제1창고", "제2창고", "원자재창고"])})
    return out


def rows_demand(rng, n):
    out, start = [], rng.randint(0, 6)
    for code, name, _ in rng.sample(PRODUCTS, len(PRODUCTS)):
        for i in range(12):
            out.append({"product_code": code, "product_name": name, "period": month(start + i), "demand_qty": str(rng.randrange(1500, 12000, 100)),
                        "unit": "EA"})
            if len(out) == n:
                return out
    return out


TABLES = {
    "product": {"req": ["product_code", "product_name", "unit", "product_type", "safety_stock"],
                "opt": ["brand", "ply", "rolls", "launch", "sale_status", "list_price"], "rows": rows_product,
                "files": ["제품마스터", "제품목록", "product_master", "완제품 기준정보"], "sheet": ["제품", "Products", "제품마스터"]},
    "material": {"req": ["material_code", "material_name", "unit", "safety_stock"],
                 "opt": ["material_kind", "main_supplier", "moq", "use_yn"], "rows": rows_material,
                 "files": ["자재마스터", "원부자재 목록", "material_master", "자재 기준정보"], "sheet": ["자재", "Materials", "자재마스터"]},
    "bom": {"req": ["bom_code", "product_code", "version", "status", "active", "valid_from", "valid_to", "base_qty", "seq", "comp_type",
                    "comp_code", "qty_per", "unit", "scrap"], "opt": [], "rows": rows_bom,
            "files": ["BOM", "자재명세서", "bom_export", "제품별 소요자재"], "sheet": ["BOM", "자재명세서", "bom"]},
    "inventory": {"req": ["item_type", "item_code", "as_of", "on_hand", "allocated", "available", "unit"], "opt": ["warehouse"],
                  "rows": rows_inventory, "files": ["재고현황", "재고조사표", "inventory_snapshot", "월말 재고"], "sheet": ["재고", "Inventory", "재고현황"]},
    "monthly_demand": {"req": ["product_code", "period", "demand_qty", "unit"], "opt": ["product_name"], "rows": rows_demand,
                       "files": ["월별수요", "월 판매실적", "monthly_demand", "수요실적"], "sheet": ["수요", "Demand", "월별수요"]},
}
NEUTRAL_FILES = ["Book1", "data", "export_20261101", "자료", "새 Microsoft Excel 워크시트", "download (3)", "첨부1", "최종", "수정본_v2"]
NOISE = [("비고", lambda r: r.choice([None, None, "확인 필요", "특이사항 없음"])), ("담당자", lambda r: r.choice(NAMES)),
         ("등록일", lambda r: day(r)), ("수정일", lambda r: day(r)), ("No.", lambda r: str(r.randint(1, 999)))]
STYLES = ("ko", "ko_alias", "en_snake", "en_title", "decorated")
DECOR = [lambda s: s + " ", lambda s: " " + s, lambda s: s + "*", lambda s: "[" + s + "]", lambda s: s + "\n(필수)",
         lambda s: s.replace("코드", " 코드"), lambda s: s + ":"]


def header(key: str, style: str, rng: random.Random) -> str:
    ko, en = COL[key]
    if style == "ko":
        return ko[0]
    if style == "ko_alias":
        return rng.choice(ko)
    if style == "en_snake":
        return en[0]
    if style == "en_title":
        return rng.choice(en).replace("_", " ").title()
    return rng.choice(DECOR)(rng.choice(ko))


def render(entity, rng, style, n, *, n_opt=None, shuffle=False, noise=0, keys=None, headers=None):
    """entity 표 하나를 (열 이름, 샘플 행) 으로 만든다. keys/headers 를 주면 그 열 구성과 표기를 그대로 쓴다."""
    spec = TABLES[entity]
    if keys is None:
        n_opt = rng.randint(0, len(spec["opt"])) if n_opt is None else n_opt
        keys = spec["req"] + rng.sample(spec["opt"], n_opt)
    keys = list(keys)
    if shuffle:
        rng.shuffle(keys)
    if headers is None:
        headers = []
        for k in keys:
            h = header(k, style, rng)
            while h in headers:
                h = header(k, "ko", rng) if header(k, "ko", rng) not in headers else h + " "
            headers.append(h)
    rows = [[r.get(k) for k in keys] for r in spec["rows"](rng, max(n, 1))][:n]
    for name, fn in rng.sample(NOISE, noise):
        pos = rng.randint(0, len(headers))
        headers.insert(pos, name)
        for row in rows:
            row.insert(pos, fn(rng))
    return list(headers), rows


# ---------------------------------------------------------------------------
# 다섯 entity 가 아닌 자료 (보류가 정답). (이름, 파일명들, 한글 열, 영문 열, 행 생성 함수)
# ---------------------------------------------------------------------------
def _p(rng):
    return rng.choice(PRODUCTS)


def _m(rng):
    return rng.choice(MATERIALS)


def r_sales(rng):
    p, c = _p(rng), rng.choice(CUSTOMERS)
    qty, price = rng.randrange(10, 600, 10), rng.randrange(6000, 14000, 100)
    d = day(rng)
    return [d, d, f"SO-{rng.randint(260000, 269999)}", str(rng.randint(1, 5)), c[0], c[1], c[2], p[0], p[1], str(qty), "EA", str(price),
            str(qty * price), rng.choice(["정상", "정상", "반품"]), None]


def r_shipment(rng):
    p = _p(rng)
    return [day(rng), f"DO-{rng.randint(10000, 99999)}", p[0], p[1], str(rng.randrange(10, 600, 10)), "EA", rng.choice(CUSTOMERS)[1]]


def r_resource(rng):
    r = rng.choice(RESOURCES)
    return [r[0], r[1], r[2], "PERSON_HOUR" if r[2] == "LABOR_POOL" else "MACHINE_HOUR", str(rng.choice([1, 1, 2, 6]))]


def r_hours(rng):
    r = rng.choice(RESOURCES)
    return [f"H-{r[0]}", r[0], month(rng.randint(24, 26)), str(rng.choice([160, 168, 176])), str(rng.choice([0, 20, 40])), "h",
            "PERSON_HOUR" if r[2] == "LABOR_POOL" else "MACHINE_HOUR", "NET", None]


def r_qty_limit(rng):
    p = _p(rng)
    return [f"Q-{p[0]}", p[0], month(rng.randint(24, 26)), str(rng.randrange(8000, 30000, 500)), "EA", "FINISHED_OUTPUT", None]


def r_routing(rng):
    p, r = _p(rng), rng.choice(RESOURCES[:5])
    op = {"RW": "REWIND", "SA": "CUT", "PK": "PACK"}[r[0][:2]]
    return [f"RT-{p[0]}", "V1", op, p[0], op, r[0], str(rng.choice([60, 120, 1000])), "EA", str(rng.choice([1, 2, 18])), "h", "MACHINE_HOUR",
            "2025-01-01", None]


def r_production(rng):
    p = _p(rng)
    qty = rng.randrange(500, 5000, 100)
    bad = rng.randint(0, 40)
    return [day(rng), f"WO-{rng.randint(260000, 269999)}", p[0], p[1], str(qty), str(qty - bad), str(bad), "EA", rng.choice(["RW1", "RW2"]),
            f"{rng.uniform(2, 9):.1f}", "SAW1", f"{rng.uniform(1, 5):.1f}", rng.choice(["PK1", "PK2"]), f"{rng.uniform(2, 9):.1f}"]


def r_issue(rng):
    p, m = _p(rng), _m(rng)
    return [day(rng), f"WO-{rng.randint(260000, 269999)}", p[0], m[0], m[1], str(rng.randrange(50, 5000, 50)), m[3]]


def r_po(rng):
    m, s = _m(rng), rng.choice(SUPPLIERS)
    qty, price = rng.randrange(1000, 20000, 500), rng.choice([25, 100, 120, 600, 1100, 1800])
    got = rng.choice([0, qty, qty // 2])
    return [day(rng), f"PO-{rng.randint(260000, 269999)}", s[0], s[1], m[0], m[1], str(qty), m[3], str(price), str(qty * price), day(rng),
            str(got), str(qty - got), rng.choice(["발주", "부분입고", "입고완료"])]


def r_receipt(rng):
    m, s = _m(rng), rng.choice(SUPPLIERS)
    qty, price = rng.randrange(1000, 20000, 500), rng.choice([25, 100, 120, 600, 1100, 1800])
    return [day(rng), f"GR-{rng.randint(260000, 269999)}", f"PO-{rng.randint(260000, 269999)}", s[0], s[1], m[0], m[1], str(qty), m[3],
            str(price), str(qty * price), "원자재창고"]


def r_ledger(rng):
    if rng.random() < 0.5:
        p = _p(rng)
        kind, code, name, unit = "제품", p[0], p[1], "EA"
    else:
        m = _m(rng)
        kind, code, name, unit = "자재", m[0], m[1], m[3]
    a, b, c = (rng.randrange(0, 20000, 100) for _ in range(3))
    return [month(rng.randint(12, 23)), kind, code, name, unit, str(a), str(b if kind == "제품" else 0), str(0 if kind == "제품" else b), "0",
            str(c if kind == "제품" else 0), str(0 if kind == "제품" else c), "0", str(a + b - c)]


def r_supplier(rng):
    s = rng.choice(SUPPLIERS)
    return [s[0], s[1], rng.choice(["원단", "지관", "포장재"]), rng.choice(["국내", "수입"]), day(rng, 2018), "월말 마감 익월 30일",
            str(rng.choice([7, 10, 14, 21, 30]))]


def r_customer(rng):
    c = rng.choice(CUSTOMERS)
    return [c[0], c[1], c[2], rng.choice(["서울", "경기", "충북", "부산"]), rng.choice(["월", "수", "금"]), day(rng, 2019), None, "월말 마감 익월 30일",
            "거래중", f"SR-{rng.randint(1, 9):02d}"]


def r_sales_price(rng):
    return [_p(rng)[0], rng.choice(CUSTOMERS)[2], str(rng.randrange(6000, 14000, 100)), "2026-03-01", None]


def r_purchase_price(rng):
    m = _m(rng)
    return [m[0], m[5], str(rng.choice([25, 100, 120, 600, 1100, 1800])), "KRW", m[3], str(rng.choice([7, 10, 14, 21])), "5000", "2026-01-01", None]


def r_hr(rng):
    return [f"E{rng.randint(1000, 9999)}", rng.choice(NAMES), rng.choice(["생산팀", "품질팀", "영업팀", "구매팀"]), rng.choice(["사원", "대리", "과장"]),
            day(rng, rng.randint(2012, 2025)), rng.choice(["재직", "재직", "휴직"])]


def r_attendance(rng):
    return [day(rng), f"E{rng.randint(1000, 9999)}", rng.choice(NAMES), "08:5" + str(rng.randint(0, 9)), "18:0" + str(rng.randint(0, 9)),
            str(rng.choice([0, 0, 1, 2])), rng.choice(["주간", "야간"])]


def r_journal(rng):
    amt = rng.randrange(10000, 9000000, 1000)
    return [day(rng), f"JV-{rng.randint(1000, 9999)}", rng.choice(["원재료", "외상매입금", "제품매출", "외상매출금", "소모품비"]),
            str(amt), "0", rng.choice(["원단 매입", "제품 매출", "소모품 구입"]), rng.choice(["가상펄프상사", "가상마트 본사"])]


def r_receivable(rng):
    c = rng.choice(CUSTOMERS)
    amt = rng.randrange(100000, 90000000, 10000)
    return [c[0], c[1], day(rng), str(amt), str(amt // 2), str(amt - amt // 2), day(rng), rng.choice(["정상", "연체"])]


def r_maintenance(rng):
    r = rng.choice(RESOURCES[:5])
    return [day(rng), r[0], r[1], rng.choice(["정기점검", "고장수리", "부품교체"]), f"{rng.uniform(0.5, 6):.1f}", rng.choice(NAMES),
            rng.choice(["완료", "진행중"])]


def r_quality(rng):
    p = _p(rng)
    n = rng.choice([50, 80, 125])
    bad = rng.randint(0, 4)
    return [day(rng), f"LOT-{rng.randint(10000, 99999)}", p[0], p[1], rng.choice(["평량", "인장강도", "외관", "롤 길이"]), str(n), str(bad),
            "합격" if bad < 3 else "불합격", rng.choice(NAMES)]


def r_dispatch(rng):
    return [day(rng), f"{rng.randint(10, 99)}가{rng.randint(1000, 9999)}", rng.choice(NAMES), rng.choice(["청주", "서울", "대전", "부산"]),
            str(rng.randint(40, 420)), str(rng.randint(4, 24)), rng.choice(CUSTOMERS)[1]]


def r_todo(rng):
    return [str(rng.randint(1, 40)), rng.choice(["설비 점검 일정 확인", "거래처 회신", "월말 결산 자료 취합", "안전 교육"]), rng.choice(NAMES),
            day(rng), rng.choice(["진행", "완료", "대기"])]


def r_energy(rng):
    return [month(rng.randint(0, 23)), rng.choice(["전기", "가스", "용수"]), str(rng.randrange(1000, 90000, 100)),
            rng.choice(["kWh", "Nm3", "ton"]), str(rng.randrange(100000, 9000000, 1000))]


def r_survey(rng):
    return [str(rng.randint(1, 300)), rng.choice(["20대", "30대", "40대", "50대"]), rng.choice(["남", "여"]), str(rng.randint(1, 5)),
            str(rng.randint(1, 5)), rng.choice(["부드러움", "가격", "포장"])]


OTHER = {
    # 변환하면 monthly_demand 가 되는 자료
    "sales_orders": (["판매현황", "수주내역", "sales_orders"],
                     ["주문일자", "출고일자", "주문번호", "행번호", "거래처코드", "거래처명", "채널", "제품코드", "제품명", "수량", "단위", "단가", "금액",
                      "구분", "원주문번호"],
                     ["order_date", "ship_date", "order_no", "line_no", "customer_id", "customer_name", "channel", "product_id",
                      "product_name", "qty", "unit", "unit_price", "amount", "order_type", "origin_order_no"], r_sales),
    "shipments": (["출고내역", "출하실적", "shipments"], ["출고일자", "출고번호", "제품코드", "제품명", "출고수량", "단위", "납품처"],
                  ["ship_date", "delivery_no", "product_id", "product_name", "ship_qty", "unit", "ship_to"], r_shipment),
    # 분류 범주에 넣지 않기로 한 자료
    "capacity_resources": (["설비목록", "자원 마스터", "resources"], ["자원코드", "자원명", "자원구분", "시간기준", "병렬대수"],
                           ["resource_id", "resource_name", "kind", "time_basis", "parallel_units"], r_resource),
    "capacity_hours": (["설비가동시간", "CAPA_시간예산", "hours_budgets"],
                       ["능력코드", "자원코드", "기준월", "정규시간", "잔업한도", "단위", "시간기준", "가용기준", "캘린더"],
                       ["capacity_id", "resource_id", "period", "regular_hours", "overtime_hours_limit", "unit", "time_basis",
                        "availability_basis", "calendar_ref"], r_hours),
    "capacity_qty_limit": (["생산한도", "월 생산가능수량", "quantity_limits"], ["능력코드", "제품코드", "기준월", "한도수량", "단위", "집계기준", "공정코드"],
                           ["capacity_id", "product_id", "period", "limit_qty", "unit", "accounting_point", "operation_id"], r_qty_limit),
    "routing": (["공정순서", "라우팅", "routing_steps"],
                ["라우팅코드", "라우팅버전", "공정순번", "제품코드", "공정코드", "자원코드", "기준수량", "수량단위", "가공시간", "시간단위", "시간기준",
                 "유효시작일", "유효종료일"],
                ["routing_id", "routing_version", "step_id", "product_id", "operation_id", "resource_id", "reference_qty", "quantity_unit",
                 "run_time", "time_unit", "time_basis", "valid_from", "valid_to"], r_routing),
    # 그 밖의 업무 보고서
    "production": (["생산실적", "작업일보", "production_results"],
                   ["생산일자", "작업지시번호", "제품코드", "제품명", "지시수량", "양품수량", "불량수량", "단위", "되감기설비", "되감기시간(h)", "절단설비",
                    "절단시간(h)", "포장설비", "포장시간(h)"],
                   ["prod_date", "work_order_no", "product_id", "product_name", "order_qty", "good_qty", "defect_qty", "unit", "rewind_machine",
                    "rewind_hours", "cut_machine", "cut_hours", "pack_machine", "pack_hours"], r_production),
    "material_issue": (["자재투입내역", "자재불출", "material_issues"], ["투입일자", "작업지시번호", "제품코드", "자재코드", "자재명", "투입수량", "단위"],
                       ["issue_date", "work_order_no", "product_id", "material_id", "material_name", "issue_qty", "unit"], r_issue),
    "purchase_orders": (["구매발주내역", "발주현황", "purchase_orders"],
                        ["발주일", "발주번호", "공급사코드", "공급사명", "자재코드", "자재명", "발주수량", "단위", "단가", "금액", "납기예정일", "입고수량",
                         "미입고수량", "진행상태"],
                        ["po_date", "po_no", "supplier_id", "supplier_name", "material_id", "material_name", "po_qty", "unit", "unit_price",
                         "amount", "due_date", "received_qty", "open_qty", "status"], r_po),
    "receipts": (["입고내역", "자재입고", "goods_receipts"],
                 ["입고일", "입고번호", "발주번호", "공급사코드", "공급사명", "자재코드", "자재명", "입고수량", "단위", "단가", "금액", "입고창고"],
                 ["receipt_date", "receipt_no", "po_no", "supplier_id", "supplier_name", "material_id", "material_name", "receipt_qty", "unit",
                  "unit_price", "amount", "warehouse"], r_receipt),
    "stock_ledger": (["재고수불부", "수불현황", "stock_ledger"],
                     ["월", "품목구분", "품목코드", "품목명", "단위", "기초재고", "생산입고", "구매입고", "반품입고", "판매출고", "생산투입", "반품폐기",
                      "기말재고"],
                     ["month", "item_type", "item_id", "item_name", "unit", "opening_qty", "production_in", "purchase_in", "return_in",
                      "sales_out", "production_out", "scrap_out", "closing_qty"], r_ledger),
    "suppliers": (["공급사목록", "협력업체", "suppliers"], ["공급사코드", "공급사명", "공급품목군", "지역", "거래시작일", "결제조건", "기본납품기간(일)"],
                  ["supplier_id", "supplier_name", "supply_group", "region", "since", "payment_terms", "lead_time_days"], r_supplier),
    "customers": (["거래처목록", "고객사", "customers"],
                  ["거래처코드", "거래처명", "채널", "지역", "발주요일", "거래시작일", "거래종료일", "결제조건", "거래상태", "담당영업코드"],
                  ["customer_id", "customer_name", "channel", "region", "order_weekday", "since", "until", "payment_terms", "status",
                   "sales_rep_id"], r_customer),
    "sales_price": (["판매단가표", "제품 공급가", "sales_price_list"], ["제품코드", "채널", "공급가", "적용시작일", "적용종료일"],
                    ["product_id", "channel", "supply_price", "valid_from", "valid_to"], r_sales_price),
    "purchase_price": (["구매단가표", "자재 단가", "purchase_price_list"],
                       ["자재코드", "공급사코드", "단가", "통화", "단위", "납품기간(일)", "최소주문량", "적용시작일", "적용종료일"],
                       ["material_id", "supplier_id", "unit_price", "currency", "unit", "lead_time_days", "min_order_qty", "valid_from",
                        "valid_to"], r_purchase_price),
    # 제조 계획과 무관한 자료
    "hr_roster": (["사원명부", "인사카드", "employees"], ["사번", "성명", "부서", "직급", "입사일", "재직상태"],
                  ["employee_id", "name", "department", "position", "hire_date", "status"], r_hr),
    "attendance": (["근태기록", "출퇴근", "attendance"], ["근무일", "사번", "성명", "출근시각", "퇴근시각", "연장근로(h)", "근무조"],
                   ["work_date", "employee_id", "name", "clock_in", "clock_out", "overtime_hours", "shift"], r_attendance),
    "journal": (["분개장", "전표내역", "journal_entries"], ["전표일자", "전표번호", "계정과목", "차변", "대변", "적요", "거래처"],
                ["entry_date", "voucher_no", "account", "debit", "credit", "memo", "partner"], r_journal),
    "receivables": (["미수금현황", "채권잔액", "receivables"], ["거래처코드", "거래처명", "청구일", "청구금액", "입금액", "잔액", "만기일", "상태"],
                    ["customer_id", "customer_name", "invoice_date", "invoice_amount", "paid_amount", "balance", "due_date", "status"],
                    r_receivable),
    "maintenance": (["설비보전이력", "수리내역", "maintenance_log"], ["작업일", "설비코드", "설비명", "작업구분", "정지시간(h)", "작업자", "상태"],
                    ["work_date", "machine_id", "machine_name", "work_type", "downtime_hours", "worker", "status"], r_maintenance),
    "quality": (["품질검사", "검사성적", "inspection"], ["검사일", "로트번호", "제품코드", "제품명", "검사항목", "시료수", "불량수", "판정", "검사자"],
                ["inspect_date", "lot_no", "product_id", "product_name", "inspect_item", "sample_size", "defect_count", "result", "inspector"],
                r_quality),
    "dispatch": (["배차일지", "차량운행", "dispatch_log"], ["운행일", "차량번호", "운전자", "도착지", "운행거리(km)", "적재팔레트", "납품처"],
                 ["trip_date", "vehicle_no", "driver", "destination", "distance_km", "pallets", "ship_to"], r_dispatch),
    "todo": (["업무목록", "회의 후속조치", "todo"], ["번호", "할 일", "담당자", "기한", "진행상태"], ["no", "task", "owner", "due_date", "status"], r_todo),
    "energy": (["에너지사용량", "유틸리티", "energy_usage"], ["월", "에너지원", "사용량", "단위", "요금"],
               ["month", "energy_type", "usage", "unit", "cost"], r_energy),
    "survey": (["고객설문", "만족도조사", "survey"], ["응답번호", "연령대", "성별", "만족도", "재구매의향", "선택이유"],
               ["response_id", "age_group", "gender", "satisfaction", "repurchase", "reason"], r_survey),
}
GROUP_OF = {**{k: "convertible" for k in ("sales_orders", "shipments")},
            **{k: "capacity_routing" for k in ("capacity_resources", "capacity_hours", "capacity_qty_limit", "routing")},
            **{k: "other_report" for k in ("production", "material_issue", "purchase_orders", "receipts", "stock_ledger", "suppliers",
                                           "customers", "sales_price", "purchase_price")},
            **{k: "unrelated" for k in ("hr_roster", "attendance", "journal", "receivables", "maintenance", "quality", "dispatch", "todo",
                                        "energy", "survey")}}


def render_other(kind, rng, lang, n):
    _, ko, en, fn = OTHER[kind]
    cols = list(ko if lang == "ko" else en)
    return cols, [fn(rng) for _ in range(n)]


# ---------------------------------------------------------------------------
# 사례 조립
# ---------------------------------------------------------------------------
class Builder:
    def __init__(self):
        self.cases, self.counter = [], {}

    def add(self, group, content, sheets, stem, fmt, *, expected=None, must_hold=False, hold_ok=False, guidance=None,
            difficulty="variant", variant=""):
        assert (expected is None) == must_hold and (expected is None or expected in ENTITIES)
        if fmt == "csv":
            assert len(sheets) == 1
            sheets = [{**sheets[0], "name": None}]
        sheets = [{"name": s["name"], "columns": list(s["columns"]), "sample_rows": [list(r) for r in s["sample_rows"]]} for s in sheets]
        filename = f"{stem}.{fmt}"
        digest = hashlib.sha256(json.dumps([filename, sheets], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        self.counter[group] = self.counter.get(group, 0) + 1
        case_id = f"{group}-{self.counter[group]:03d}"
        split = "dev" if int(hashlib.sha256(case_id.encode()).hexdigest()[:8], 16) % 10 < 4 else "test"
        self.cases.append({
            "case_id": case_id, "split": split, "group": group, "content": content, "difficulty": difficulty, "variant": variant,
            "expected": {"expected_entity": expected, "must_hold": must_hold, "hold_ok": hold_ok, "guidance_entity": guidance},
            "payload": {"filename": filename, "sha256": digest, "format": fmt, "sheets": sheets},
        })


def sheet(name, columns, rows):
    return {"name": name, "columns": columns, "sample_rows": rows}


def build() -> list[dict]:
    rng = random.Random(SEED)
    b = Builder()

    def stem_for(entity, mode="hint"):
        if mode == "neutral":
            return rng.choice(NEUTRAL_FILES)
        if mode == "wrong":
            return rng.choice(TABLES[rng.choice([e for e in ENTITIES if e != entity])]["files"])
        return rng.choice(TABLES[entity]["files"]) + rng.choice(["", "", "_2026", "_최종", " (1)"])

    # 1) 다섯 entity: 표기 5종 x 샘플 행 0/5/20
    for entity in ENTITIES:
        spec = TABLES[entity]
        i = 0
        for style in STYLES:
            for n in (0, 5, 20):
                shuffle, noise = rng.random() < 0.5, rng.choice([0, 0, 1, 2])
                cols, rows = render(entity, rng, style, n, shuffle=shuffle, noise=noise)
                fmt = "csv" if i % 2 == 0 else "xlsx"
                mode = "neutral" if i % 3 == 2 else "hint"
                tags = [style, f"rows{n}", f"file_{mode}"] + (["shuffled"] if shuffle else []) + ([f"noise{noise}"] if noise else [])
                b.add(entity, entity, [sheet(rng.choice(spec["sheet"]), cols, rows)], stem_for(entity, mode), fmt, expected=entity,
                      difficulty="easy" if style in ("ko", "en_snake") and not noise and not shuffle else "variant", variant=",".join(tags))
                i += 1

        # 설명 시트·빈 시트가 함께 있는 통합 문서
        for n in (0, 5):
            cols, rows = render(entity, rng, "ko_alias", n)
            notes = sheet("작성안내", ["작성 안내"], [["노란 칸만 입력하세요."], ["문의: 생산관리팀"]] if n else [])
            b.add(entity, entity, [sheet(rng.choice(spec["sheet"]), cols, rows), notes], stem_for(entity), "xlsx", expected=entity,
                  hold_ok=True, variant=f"notes_sheet,rows{n}")
        cols, rows = render(entity, rng, "ko", 5)
        b.add(entity, entity, [sheet("Sheet1", cols, rows), sheet("Sheet2", [], []), sheet("Sheet3", [], [])], stem_for(entity, "neutral"),
              "xlsx", expected=entity, hold_ok=True, variant="empty_sheets,rows5")

        # 표 위에 제목 줄이 있어 첫 행이 열 이름이 아닌 파일
        cols, rows = render(entity, rng, "ko", 4)
        title = [f"㈜충파모제지 {rng.choice(spec['files'])} (2026년 11월 기준)"] + [""] * (len(cols) - 1)
        blank = [None] * len(cols)
        b.add(entity, entity, [sheet("Sheet1", title, [])], stem_for(entity, "neutral"), "xlsx", must_hold=True, difficulty="hard",
              variant="title_row,rows0")
        b.add(entity, entity, [sheet("Sheet1", title, [blank, cols] + rows)], stem_for(entity, "neutral"), "xlsx", expected=entity, hold_ok=True,
              difficulty="hard", variant="title_row,rows6")

        # 다른 종류를 가리키는 파일명
        cols, rows = render(entity, rng, "ko", 0)
        b.add(entity, entity, [sheet(None, cols, rows)], stem_for(entity, "wrong"), "csv", expected=entity, hold_ok=True, difficulty="hard",
              variant="file_wrong,rows0")

        # 중복 열 이름, 끝에 붙은 빈 열
        cols, rows = render(entity, rng, "ko_alias", 5)
        b.add(entity, entity, [sheet("Sheet1", cols + ["비고", "비고"], [r + [None, "확인"] for r in rows])], stem_for(entity), "xlsx",
              expected=entity, variant="duplicate_header,rows5")
        cols, rows = render(entity, rng, "en_snake", 5)
        b.add(entity, entity, [sheet(None, cols + ["", ""], [r + [None, None] for r in rows])], stem_for(entity), "csv", expected=entity,
              variant="blank_trailing_columns,rows5")

    # 1-b) 필수 열 일부가 빠진 파일: 종류는 알 수 있으므로 추천하고, 빠진 열은 뒤의 검증 단계가 잡는다
    keep = {"product": ["product_code", "product_name", "unit"], "material": ["material_code", "material_name", "unit"],
            "bom": ["product_code", "seq", "comp_code", "qty_per", "unit"], "inventory": ["item_type", "item_code", "as_of", "on_hand"],
            "monthly_demand": ["product_code", "period", "demand_qty"]}
    for entity in ENTITIES:
        for style, n in (("ko", 0), ("ko_alias", 5), ("en_snake", 5)):
            cols, rows = render(entity, rng, style, n, keys=keep[entity])
            b.add(entity, entity, [sheet(None, cols, rows)], stem_for(entity), "csv", expected=entity, hold_ok=True, difficulty="hard",
                  variant=f"missing_required,{style},rows{n}")

    # 1-c) 같은 종류의 시트가 여러 개인 통합 문서: 시트가 여러 개라는 이유만으로 보류하면 안 된다
    same_sheets = {"product": ["순수", "데일리", "에코"], "material": ["원단", "부자재", "포장재"], "bom": ["3겹", "2겹"],
                   "inventory": ["제1창고", "제2창고", "원자재창고"], "monthly_demand": ["2024", "2025", "2026"]}
    for entity in ENTITIES:
        for n in (0, 5):
            heads, _ = render(entity, rng, "ko", 0, keys=TABLES[entity]["req"])
            sheets = [sheet(name, heads, render(entity, rng, "ko", n, keys=TABLES[entity]["req"], headers=heads)[1]) for name in same_sheets[entity]]
            b.add(entity, entity, sheets, stem_for(entity), "xlsx", expected=entity, variant=f"same_entity_sheets,rows{n}")

    # 2) 열 구성이 최소이거나 일반 표기를 써서 헷갈리는 정답 사례
    def confuser(entity, keys, headers, n, tag):
        cols, rows = render(entity, rng, "ko", n, keys=keys, headers=headers)
        b.add("confuser", entity, [sheet(None, cols, rows)], stem_for(entity, "neutral"), "csv", expected=entity, hold_ok=True,
              difficulty="hard", variant=f"{tag},rows{n}")

    for n in (0, 5):
        confuser("product", ["product_code", "product_name", "unit", "product_type", "safety_stock"],
                 ["품목코드", "품목명", "단위", "제품유형", "안전재고"], n, "generic_code_with_product_type")
        confuser("material", ["material_code", "material_name", "material_kind", "unit", "moq", "safety_stock"],
                 ["품목코드", "품목명", "자재구분", "단위", "최소주문량", "안전재고"], n, "generic_code_with_material_fields")
        confuser("inventory", ["item_code", "as_of", "on_hand", "unit"], ["품목코드", "기준일", "현재고", "단위"], n, "inventory_minimal")
        confuser("monthly_demand", ["product_code", "period", "demand_qty", "unit"], ["제품코드", "기준월", "수량", "단위"], n,
                 "demand_generic_qty")
        confuser("bom", ["product_code", "comp_code", "qty_per", "unit"], ["모품목코드", "자품목코드", "소요량", "단위"], n, "bom_minimal")
    confuser("inventory", ["item_code", "warehouse", "as_of", "on_hand", "available", "unit"],
             ["Item Code", "Warehouse", "Stock Date", "On Hand", "Available", "UOM"], 5, "inventory_en_title")
    confuser("monthly_demand", ["product_code", "period", "demand_qty"], ["sku", "month", "qty"], 5, "demand_en_short")
    confuser("bom", ["product_code", "comp_code", "qty_per", "unit"], ["parent_item", "component", "qty_per", "uom"], 5, "bom_en_minimal")
    confuser("product", ["product_code", "product_name", "brand", "ply", "rolls", "unit", "list_price"],
             ["SKU", "Description", "Brand", "Ply", "Rolls", "UOM", "List Price"], 5, "product_catalog_en")

    # 3) 다섯 entity 가 아닌 자료: 보류가 정답
    for kind, (stems, _, _, _) in OTHER.items():
        group = GROUP_OF[kind]
        guidance = "monthly_demand" if group == "convertible" else None
        plans = [("ko", 0), ("ko", 5), ("en", 5)] + ([("ko", 20), ("en", 0), ("en", 20)] if group == "convertible" else []) \
            + ([("en", 0)] if group == "capacity_routing" else [])
        if group == "unrelated":
            plans = [("ko", 0), ("ko", 5)]
        for j, (lang, n) in enumerate(plans):
            cols, rows = render_other(kind, rng, lang, n)
            fmt = "csv" if j % 2 == 0 else "xlsx"
            stem = stems[2] if lang == "en" else rng.choice(stems[:2])
            if j == len(plans) - 1 and group != "unrelated":
                stem = rng.choice(NEUTRAL_FILES)
            b.add(group, kind, [sheet("Sheet1", cols, rows)], stem, fmt, must_hold=True, guidance=guidance,
                  difficulty="hard" if group in ("convertible", "other_report") else "variant", variant=f"{lang},rows{n}")

    # 가로로 펼친 월별 수요표: 그대로는 올릴 수 없고 세로로 바꿔야 한다
    for j, (heads, n) in enumerate([(["제품코드", "제품명"], 0), (["제품코드", "제품명"], 5), (["품번"], 5), (["product_id"], 0), (["product_id"], 5),
                                     (["제품코드", "구분"], 20)]):
        months = [month(12 + i) for i in range(12)] if j % 2 == 0 else [f"{i}월" for i in range(1, 13)]
        rows = []
        for code, name, _ in rng.sample(PRODUCTS, min(n, len(PRODUCTS))):
            lead = [code, name] if len(heads) == 2 and heads[1] == "제품명" else [code, "판매"] if len(heads) == 2 else [code]
            rows.append(lead + [str(rng.randrange(1500, 12000, 100)) for _ in months])
        b.add("convertible", "demand_wide_pivot", [sheet("Sheet1", heads + months, rows)], rng.choice(["월별 판매실적", "수요실적_가로", "sales_by_month"]),
              "xlsx" if j % 2 else "csv", must_hold=True, guidance="monthly_demand", difficulty="hard", variant=f"wide_months,rows{n}")

    # 4) 열 이름만으로는 종류를 정할 수 없는 자료
    def generic_item_rows(n, with_kind=False):
        items = [("제품", c, nm, "EA", s) for c, nm, s in PRODUCTS] + [("자재", m[0], m[1], m[3], m[4]) for m in MATERIALS]
        picked = rng.sample(items, min(n, len(items)))
        return [list(r if with_kind else r[1:]) for r in picked]

    for heads, n in [(["품목코드", "품목명", "단위", "안전재고"], 0), (["품목코드", "품목명", "단위", "안전재고"], 5), (["품번", "품명", "단위"], 0),
                     (["품번", "품명", "단위"], 5), (["item_code", "item_name", "unit", "safety_stock"], 0), (["코드", "명칭", "단위", "안전재고"], 5)]:
        rows = [r[:len(heads)] for r in generic_item_rows(n)]
        b.add("ambiguous", "generic_item_master", [sheet(None, heads, rows)], rng.choice(["품목마스터", "기준정보", "item_master"]), "csv",
              must_hold=True, difficulty="hard", variant=f"product_or_material,rows{n}")
    for n in (0, 5, 20):
        rows = generic_item_rows(n, with_kind=True)
        b.add("ambiguous", "mixed_item_master", [sheet("품목", ["품목구분", "품목코드", "품목명", "단위", "안전재고"], rows)], "품목마스터_전체", "xlsx",
              must_hold=True, difficulty="hard", variant=f"products_and_materials_in_one_sheet,rows{n}")
    for heads, n in [(["품목코드", "일자", "수량", "단위"], 0), (["품목코드", "일자", "수량", "단위"], 5), (["item_code", "date", "qty"], 5),
                     (["코드", "날짜", "수량"], 0)]:
        rows = [[rng.choice(PRODUCTS)[0], day(rng), str(rng.randrange(10, 9000, 10)), "EA"][:len(heads)] for _ in range(n)]
        b.add("ambiguous", "item_date_qty", [sheet(None, heads, rows)], rng.choice(NEUTRAL_FILES), "csv", must_hold=True, difficulty="hard",
              variant=f"inventory_or_demand_or_transactions,rows{n}")

    # 한 파일에 서로 다른 종류의 시트가 들어 있는 통합 문서
    for pair, n in [(("product", "material"), 0), (("product", "material"), 5), (("product", "bom"), 5), (("monthly_demand", "inventory"), 5),
                    (("material", "bom", "inventory"), 0), (("product", "material", "bom", "inventory", "monthly_demand"), 5)]:
        sheets = []
        for e in pair:
            cols, rows = render(e, rng, "ko", n)
            sheets.append(sheet(TABLES[e]["sheet"][0], cols, rows))
        b.add("ambiguous", "mixed_workbook:" + "+".join(pair), sheets, rng.choice(["기준정보_통합", "ERP_export", "업로드자료"]), "xlsx",
              must_hold=True, difficulty="hard", variant=f"multiple_entities,rows{n}")

    # 5) 내용이 없거나 구조를 알 수 없는 파일
    cols, rows = render("product", rng, "ko", 5, n_opt=0)
    degenerate = [
        ("empty_sheet", [sheet("Sheet1", [], [])], "xlsx"),
        ("empty_sheets", [sheet("Sheet1", [], []), sheet("Sheet2", [], [])], "xlsx"),
        ("blank_headers", [sheet(None, ["", "", "", ""], [])], "csv"),
        ("blank_headers_with_rows", [sheet(None, ["", "", "", "", ""], rows)], "csv"),
        ("unnamed_headers", [sheet("Sheet1", [f"Unnamed: {i}" for i in range(5)], rows)], "xlsx"),
        ("single_column", [sheet(None, ["코드"], [[p[0]] for p in PRODUCTS[:5]])], "csv"),
        ("numeric_headers", [sheet(None, ["1", "2", "3", "4"], [["CP-N3-3030", "2026-01", "8400", "EA"]])], "csv"),
        ("free_text", [sheet("Sheet1", ["11월 생산회의 메모"], [["원단 입고 지연 건 확인"], ["다음 주 설비 점검"]])], "xlsx"),
        ("data_as_header", [sheet(None, ["CP-N3-3030", "천연펄프 3겹 30m 30롤", "EA", "완제품", "1000"], rows[:3])], "csv"),
    ]
    for tag, sheets, fmt in degenerate:
        b.add("degenerate", tag, sheets, rng.choice(NEUTRAL_FILES), fmt, must_hold=True, variant=tag)
    return b.cases


def write(cases: list[dict]) -> None:
    (HERE / "cases.json").write_text(json.dumps({"seed": SEED, "note": "SYNTHETIC. 실제 기업 자료가 아니다.", "cases": cases},
                                                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (HERE / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "split", "group", "content", "expected_entity", "must_hold", "hold_ok", "guidance_entity", "difficulty",
                    "variant", "filename", "n_sheets", "n_columns", "n_sample_rows"])
        for c in cases:
            e, p = c["expected"], c["payload"]
            w.writerow([c["case_id"], c["split"], c["group"], c["content"], e["expected_entity"] or "", e["must_hold"], e["hold_ok"],
                        e["guidance_entity"] or "", c["difficulty"], c["variant"], p["filename"], len(p["sheets"]),
                        sum(len(s["columns"]) for s in p["sheets"]), sum(len(s["sample_rows"]) for s in p["sheets"])])


if __name__ == "__main__":
    built = build()
    write(built)
    by_group: dict[str, int] = {}
    for case in built:
        by_group[case["group"]] = by_group.get(case["group"], 0) + 1
    print(len(built), by_group)
