"""㈜충파모제지 합성 데이터 생성기 (SYNTHETIC).

두루마리 화장지 가공 회사(점보롤 원단을 사서 되감기 → 절단 → 포장)를 가정한 가상 데이터다.
실제 기업의 데이터·규격·수치가 아니다. 표준 라이브러리만 쓰며, 같은 SEED면 항상 같은 파일이 나온다.

실행 (저장소 루트에서):
    python modules/planning_engine/synthetic/generate.py

출력: modules/planning_engine/synthetic/data/   (실행할 때마다 새로 만든다)
    raw/       회사가 가진 원본 (회사 양식·한글 파일명)
               master/ 기준정보, plans/ 생산팀 계획표, transactions/ 판매 현황, snapshots/ 기준일 현황
    upload/    대영 님 업로드 형식 CSV. 전부 convert.py가 raw에서 변환한 것
    derived/   분석용 집계 (원가 표, 반품 집계, 입고 예정). 역시 raw에서 변환
    errors/    검증 테스트용 오류 파일
생성기는 업로드·집계 파일의 기대값을 내부 값으로 따로 계산해 두고, raw에서 변환한 결과와 한 글자라도 다르면 멈춘다.
"""
from __future__ import annotations

import csv
import io
import json
import math
import random
import shutil
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert  # noqa: E402
import masters  # noqa: E402
import sales_orders  # noqa: E402

SEED = 20261115
COMPANY = "㈜충파모제지 (SYNTHETIC)"
OUT = Path(__file__).resolve().parent / "data"

HISTORY_START = (2022, 1)
HISTORY_END = (2026, 12)          # 60개월. 예측 기준일 trained_until = 2026-12-31
AS_OF_DATE = "2026-12-31"
PLAN_MONTHS = ["2027-01", "2027-02", "2027-03"]

# ---------------------------------------------------------------------------
# 1. 제품: (코드, 이름, 기준 월판매량, 월 추세, 출시월, 판매 패턴)
#    판매 패턴: MAIN(주력·행사), STEADY, GIFT(명절 선물), LUMPY(업소용 대량 주문)
# ---------------------------------------------------------------------------
PRODUCTS = [
    ("CP-N3-3030", "천연펄프 3겹 30m 30롤", 9000, 0.0015, None, "MAIN"),
    ("CP-N3-2730", "천연펄프 3겹 27m 30롤", 6000, 0.0010, None, "MAIN"),
    ("CP-N3-2524", "천연펄프 3겹 25m 24롤", 3000, 0.0010, None, "STEADY"),
    ("CP-N2-3030", "천연펄프 2겹 30m 30롤", 4500, -0.0060, None, "STEADY"),
    ("CP-R2-3030", "재생펄프 2겹 30m 30롤", 3500, 0.0000, None, "STEADY"),
    ("CP-P4-2524", "프리미엄 4겹 25m 24롤", 1200, 0.0120, None, "MAIN"),
    ("CP-GIFT-12", "명절 선물용 3겹 30m 12롤 세트", 200, 0.0000, None, "GIFT"),
    ("CP-ON3-3030", "온라인 전용 3겹 30m 30롤", 1500, 0.0080, (2025, 7), "MAIN"),
    ("CP-B2-JUMBO", "업소용 점보롤 2겹 300m 16롤", 800, 0.0020, None, "LUMPY"),
]

# 설·추석 날짜. 구매는 명절 2주 전쯤 몰리므로 15일 이전 명절은 앞 달을 성수기로 본다.
HOLIDAYS = ["2022-02-01", "2022-09-10", "2023-01-22", "2023-09-29", "2024-02-10", "2024-09-17",
            "2025-01-29", "2025-10-06", "2026-02-17", "2026-09-25", "2027-02-07", "2027-09-15"]

# ---------------------------------------------------------------------------
# 2. 자재와 BOM: 자재 마스터·제품 규격(masters.py)에서 만든다
#    자재: (코드, 이름, 단위, 안전재고)
# ---------------------------------------------------------------------------
MATERIALS = [(m[0], m[1], m[3], m[9]) for m in masters.MATERIALS]

# 포장재: 제품마다 1팩에 1개
PACKAGING = {"CP-N3-3030": "MP-FILM30", "CP-N3-2730": "MP-FILM30", "CP-N3-2524": "MP-FILM24",
             "CP-N2-3030": "MP-FILM30", "CP-R2-3030": "MP-FILM30", "CP-P4-2524": "MP-FILM24",
             "CP-GIFT-12": "MP-GIFTBOX", "CP-ON3-3030": "MP-FILM30", "CP-B2-JUMBO": "MP-JUMBOBOX"}
SCRAP_RATE = {"MR-R2": "0.04"}            # 원단 재단 손실. 재생지 4%, 나머지 원단 3%


def bom_lines(product):
    """[(자재, 1팩당 소요량, 단위, 스크랩률)]. 원단량은 제품 규격 × 원단 평량, 지관은 롤 수만큼."""
    _, paper, _, _, rolls, *_ = masters.PRODUCT_SPEC[product]
    return [(paper, masters.paper_kg_per_pack(product), "kg", SCRAP_RATE.get(paper, "0.03")),
            ("MC-CORE", rolls, "EA", "0"), (PACKAGING[product], 1, "EA", "0")]


BOM = {code: bom_lines(code) for code in masters.PRODUCT_SPEC}

# ---------------------------------------------------------------------------
# 3. 설비·인력과 공정
# ---------------------------------------------------------------------------
RESOURCES = [
    ("RW1", "되감기·엠보기 1호 (3겹·4겹)", "EQUIPMENT", "MACHINE_HOUR", 1),
    ("RW2", "되감기·엠보기 2호 (2겹·업소용)", "EQUIPMENT", "MACHINE_HOUR", 1),
    ("SAW1", "롤 절단기 (전 제품 공용)", "EQUIPMENT", "MACHINE_HOUR", 1),
    ("PK1", "포장기 1호 (30롤)", "EQUIPMENT", "MACHINE_HOUR", 1),
    ("PK2", "포장기 2호 (24롤·선물·업소용)", "EQUIPMENT", "MACHINE_HOUR", 1),
    ("LB1", "포장 작업자 풀", "LABOR_POOL", "PERSON_HOUR", 6),
]

# 제품군별 공정: 각 공정 = (설비, 기준수량(팩), 기계시간). 포장 공정에는 작업자 인시가 같이 붙는다.
ROUTE_30_3PLY = [("REWIND", "RW1", 70, 1), ("CUT", "SAW1", 60, 1), ("PACK", "PK1", 80, 1)]
ROUTE_30_2PLY = [("REWIND", "RW2", 80, 1), ("CUT", "SAW1", 60, 1), ("PACK", "PK1", 80, 1)]
ROUTE_24 = [("REWIND", "RW1", 85, 1), ("CUT", "SAW1", 75, 1), ("PACK", "PK2", 90, 1)]
ROUTES = {
    "CP-N3-3030": ROUTE_30_3PLY, "CP-N3-2730": ROUTE_30_3PLY, "CP-ON3-3030": ROUTE_30_3PLY,
    "CP-N2-3030": ROUTE_30_2PLY, "CP-R2-3030": ROUTE_30_2PLY,
    "CP-N3-2524": ROUTE_24, "CP-P4-2524": [("REWIND", "RW1", 70, 1), ("CUT", "SAW1", 75, 1), ("PACK", "PK2", 90, 1)],
    "CP-GIFT-12": [("REWIND", "RW1", 170, 1), ("CUT", "SAW1", 150, 1), ("PACK", "PK2", 60, 1)],
    "CP-B2-JUMBO": [("REWIND", "RW2", 30, 1), ("CUT", "SAW1", 40, 1), ("PACK", "PK2", 50, 1)],
}
LABOR_PER_1000_PACKS = {"PK1": 20, "PK2": 24}   # 포장 1,000팩당 인시
OPERATION_NAME = {"REWIND": "되감기·엠보", "CUT": "절단", "PACK": "포장"}
# 설비 목록 원본에만 있는 정보: (담당 공정, 도입 연도, 비고)
RESOURCE_INFO = {
    "RW1": ("되감기·엠보", 2016, "3겹·4겹 원단 전용"),
    "RW2": ("되감기·엠보", 2019, "2겹·재생·업소용 점보롤"),
    "SAW1": ("절단", 2016, "전 제품 공용, 예비기 없음"),
    "PK1": ("포장", 2016, "30롤 포장"),
    "PK2": ("포장", 2020, "24롤·선물세트·업소용 포장"),
    "LB1": ("포장", "", "포장 공정 작업자 6명, 2교대"),
}

# 월 가용시간 (명시 입력). 설계 기준: 2027-01 예측 기본값(MA12) 생산 필요량에서
# 절단기 SAW1 가동률 약 90%(일부러 빠듯함), 작업자 약 84%, 나머지 설비 약 70~75%.
# 2월은 설 연휴(2027-02-06~09)로 정규시간이 약 15% 적다.
# (설비/인력: {월: (정규, 잔업 한도)})
HOURS = {
    "RW1": {"2027-01": (400, 40), "2027-02": (340, 40), "2027-03": (400, 40)},
    "RW2": {"2027-01": (140, 20), "2027-02": (120, 20), "2027-03": (140, 20)},
    "SAW1": {"2027-01": (500, 40), "2027-02": (430, 40), "2027-03": (500, 40)},
    "PK1": {"2027-01": (370, 40), "2027-02": (310, 40), "2027-03": (370, 40)},
    "PK2": {"2027-01": (110, 20), "2027-02": (90, 20), "2027-03": (110, 20)},
    "LB1": {"2027-01": (690, 60), "2027-02": (590, 60), "2027-03": (690, 60)},
}
# 월 생산수량 한도: 선물세트는 박스 조립을 외부에 맡겨 월 2,500세트까지만 가능하다고 가정
QUANTITY_LIMITS = [("Q-GIFT", "CP-GIFT-12", m, 2500) for m in PLAN_MONTHS]

# ---------------------------------------------------------------------------
# 4. 원가 자료 (업로드 형식에 아직 없음 → extra/). 자재 단가·납품 기간은 구매 단가표(raw/master)에 있다.
# ---------------------------------------------------------------------------
MATERIAL_COST = masters.current_material_cost()   # 현재(2026년) 구매 단가, 원/단위
RESOURCE_COST = {  # 원/시간 (정규, 잔업)
    "RW1": (45000, 67500), "RW2": (45000, 67500), "SAW1": (40000, 60000),
    "PK1": (30000, 45000), "PK2": (30000, 45000), "LB1": (18000, 27000),
}
HOLDING_COST_RATE = Decimal("0.02")   # 월 재고유지비 = 제품 원가의 2% (가정)
# 입고 예정: 빠듯한 3겹 원단에 1월 하순 입고분이 잡혀 있다고 가정
SCHEDULED_RECEIPTS = [("PO-2701-001", "MR-N3", 10000, "kg", "2027-01-20", "SUP-PULP-A")]

# ---------------------------------------------------------------------------
# 도우미
# ---------------------------------------------------------------------------
def months(start, end):
    y, m = start
    while (y, m) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def ym(y, m):
    return f"{y:04d}-{m:02d}"


def holiday_months():
    peak = set()
    for d in HOLIDAYS:
        y, m, day = map(int, d.split("-"))
        if day < 15:
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        peak.add(ym(y, m))
    return peak


def dec(x, places=4):
    q = Decimal(1).scaleb(-places)
    s = format(Decimal(x).quantize(q, rounding=ROUND_HALF_UP).normalize(), "f")
    return s


def csv_text(header, rows) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def write_csv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# ---------------------------------------------------------------------------
# 판매 이력 생성
# ---------------------------------------------------------------------------
def generate_demand(rng: random.Random):
    peaks = holiday_months()
    history = list(months(HISTORY_START, HISTORY_END))
    demand = {}
    for code, _, base, trend, launch, pattern in PRODUCTS:
        series = []
        for k, (y, m) in enumerate(history):
            if launch and (y, m) < launch:
                continue
            period = ym(y, m)
            level = base * (1 + trend) ** k
            if launch:                                   # 출시 후 6개월 동안 서서히 증가
                age = sum(1 for p in history if launch <= p <= (y, m))
                level *= min(1.0, age / 6)
            season = 1.0
            if pattern == "GIFT":
                season = 10.0 if period in peaks else 1.0
            else:
                season *= {7: 0.96, 8: 0.96, 11: 1.06, 12: 1.04}.get(m, 1.0)
                if period in peaks:
                    season *= 1.06
            if pattern == "MAIN" and rng.random() < 0.08:  # 할인 행사 달
                season *= 1.20
            if pattern == "LUMPY":
                r = rng.random()
                season *= 1.6 if r < 0.15 else (0.7 if r > 0.9 else 1.0)
            noise = max(0.7, rng.gauss(1.0, 0.05))
            qty = int(round(level * season * noise / 10.0)) * 10
            series.append((period, max(qty, 0)))
        demand[code] = series
    return demand


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------
def main():
    rng = random.Random(SEED)
    demand = generate_demand(rng)

    # 안전재고 = 최근 12개월 평균의 10%, 기초 완제품 재고 = 최근 12개월 평균의 25% (10 단위)
    ma12 = {c: sum(q for _, q in s[-12:]) / 12 for c, s in demand.items()}
    ss = {c: int(round(ma12[c] * 0.10 / 10)) * 10 for c in demand}
    fg_inv = {c: int(round(ma12[c] * 0.25 / 10)) * 10 for c in demand}

    # 생성 결과 폴더는 매번 새로 만든다 (예전 구조의 파일이 남지 않게)
    if OUT.exists():
        shutil.rmtree(OUT)
    raw, up, derived = OUT / "raw", OUT / "upload", OUT / "derived"
    master_dir = raw / "master"

    # ---- 기준정보(마스터) ----
    years = list(range(HISTORY_START[0], HISTORY_END[0] + 1))
    names = {c: n for c, n, *_ in PRODUCTS}
    product_master = masters.product_rows(names, ss, years[0], years[-1])
    material_master = masters.material_rows()
    sales_prices = masters.sales_price_rows(years[0], years[-1])
    customer_master = masters.customer_rows()
    write_csv(master_dir / "공급사목록.csv", masters.SUPPLIER_HEADER, masters.supplier_rows())
    write_csv(master_dir / "자재마스터.csv", masters.MATERIAL_HEADER, material_master)
    write_csv(master_dir / "구매단가표.csv", masters.PURCHASE_PRICE_HEADER, masters.purchase_price_rows())
    write_csv(master_dir / "제품마스터.csv", masters.PRODUCT_HEADER, product_master)
    write_csv(master_dir / "판매단가표.csv", masters.SALES_PRICE_HEADER, sales_prices)
    write_csv(master_dir / "거래처목록.csv", masters.CUSTOMER_HEADER, customer_master)

    # ---- 업로드 파일의 기대값: 생성기 내부 값으로 직접 계산해 두고, 나중에 raw → convert.py 결과와 대조한다 ----
    expected = {}

    def expect(path: Path, header, rows):
        expected[path] = csv_text(header, rows)

    pcol = {h: i for i, h in enumerate(masters.PRODUCT_HEADER)}
    expect(up / "01_products.csv", ["제품코드", "제품명", "단위", "제품유형", "안전재고"],
           [(r[pcol["제품코드"]], r[pcol["제품명"]], r[pcol["기준단위"]], r[pcol["제품유형"]], r[pcol["안전재고"]])
            for r in product_master])
    mcol = {h: i for i, h in enumerate(masters.MATERIAL_HEADER)}
    expect(up / "02_materials.csv", ["자재코드", "자재명", "단위", "안전재고"],
           [(r[mcol["자재코드"]], r[mcol["자재명"]], r[mcol["단위"]], r[mcol["안전재고"]]) for r in material_master])
    bom_rows = []
    for code, lines in BOM.items():
        for i, (mat, qty, unit, scrap) in enumerate(lines, 1):
            bom_rows.append((f"BOM-{code}", code, "V1", "APPROVED", "Y", "2022-01-01", "", 1, i,
                             "MATERIAL", mat, dec(qty), unit, scrap))
    expect(up / "03_bom.csv", ["BOM코드", "제품코드", "버전", "상태", "활성", "유효시작일", "유효종료일",
                               "기준수량", "순번", "구성유형", "구성품코드", "소요량", "단위", "스크랩률"], bom_rows)
    mat_name = {m[0]: m[1] for m in MATERIALS}
    write_csv(master_dir / "BOM.csv",
              ["BOM번호", "제품코드", "제품명", "버전", "승인상태", "사용여부", "적용시작일", "적용종료일", "기준수량",
               "순번", "자재코드", "자재명", "소요량", "단위", "손실률(%)"],
              [(b[0], b[1], names[b[1]], b[2], "승인", b[4], b[5], b[6], b[7], b[8], b[10], mat_name[b[10]], b[11],
                "개" if b[12] == "EA" else b[12], format((Decimal(b[13]) * 100).normalize(), "f")) for b in bom_rows])

    # 다음 달 자재 소요 어림값(예측 기본값 MA12 기준)으로 재고를 정한다. MR-N3만 빠듯하게 둔다.
    need = {c: max(0, math.ceil(ma12[c] + ss[c] - fg_inv[c])) for c in demand}
    mat_req = {m[0]: Decimal(0) for m in MATERIALS}
    for code, lines in BOM.items():
        for mat, qty, _, scrap in lines:
            mat_req[mat] += need[code] * Decimal(qty) * (1 + Decimal(scrap))
    mat_ss = {c: Decimal(s) for c, *_, s in MATERIALS}
    mat_inv = {}
    for mat, req in mat_req.items():
        factor = Decimal("1.08") if mat == "MR-N3" else Decimal("1.8")
        mat_inv[mat] = int(math.ceil((req * factor + mat_ss[mat]) / 100)) * 100
    inv_rows = [("PRODUCT", c, AS_OF_DATE, fg_inv[c], 0, fg_inv[c], "EA") for c in demand]
    inv_rows += [("MATERIAL", c, AS_OF_DATE, mat_inv[c], 0, mat_inv[c], u) for c, _, u, _ in MATERIALS]
    expect(up / "04_inventory.csv", ["품목구분", "품목코드", "기준일", "현재고", "할당재고", "가용재고", "단위"], inv_rows)
    mat_kind = {m[0]: m[2] for m in masters.MATERIALS}
    write_csv(raw / "snapshots" / "재고현황_20261231.csv",
              ["기준일", "창고", "품목구분", "품목코드", "품목명", "현재고", "할당재고", "가용재고", "단위"],
              [(AS_OF_DATE, "완제품창고", "제품", c, names[c], fg_inv[c], 0, fg_inv[c], "팩") for c in demand] +
              [(AS_OF_DATE, "원자재창고" if mat_kind[c] == "원단" else "부자재창고",
                {"원단": "원자재"}.get(mat_kind[c], mat_kind[c]), c, n, mat_inv[c], 0, mat_inv[c], "개" if u == "EA" else u)
               for c, n, u, _ in MATERIALS])

    # ---- 판매 내역 보고서(주문 건별): 마스터를 조합해 만든다 ----
    price_book = masters.SalesPriceBook(sales_prices)
    customer_defs = [(c, n, ch, rg, days, w, s, e) for c, n, ch, rg, days, w, s, e in masters.CUSTOMERS]
    order_rows = sales_orders.build(demand, names, years, SEED + 1, customer_defs, price_book, masters.channel_shares)
    for y in years:
        write_csv(raw / "transactions" / f"판매현황_{y}.csv", sales_orders.HEADER,
                  [r for r in order_rows if r[0].startswith(str(y))])
    write_dirty_sample(order_rows, OUT / "errors" / "sales_orders_dirty_sample.csv")
    verify_report_against_masters(order_rows, product_master, customer_master, price_book, bom_rows)
    expect(up / "05_monthly_demand.csv", ["product_id", "period", "demand_qty", "unit"],
           [(c, p, q, "EA") for c, s in demand.items() for p, q in s if q > 0])

    # ---- 설비·생산 기준정보와 생산팀 계획표 ----
    write_csv(master_dir / "설비목록.csv", ["설비코드", "설비명", "구분", "담당공정", "대수·인원", "도입연도", "비고"],
              [(r, n, "작업자" if kind == "LABOR_POOL" else "설비", RESOURCE_INFO[r][0], units, RESOURCE_INFO[r][1],
                RESOURCE_INFO[r][2]) for r, n, kind, _, units in RESOURCES])
    expect(up / "06_capacity_resources.csv", ["resource_id", "resource_name", "kind", "time_basis", "parallel_units"],
           RESOURCES)
    expect(up / "07_capacity_quantity_limits.csv",
           ["capacity_id", "product_id", "period", "limit_qty", "unit", "accounting_point", "operation_id"],
           [(cid, p, m, q, "EA", "FINISHED_OUTPUT", "") for cid, p, m, q in QUANTITY_LIMITS])
    write_csv(raw / "plans" / "월별생산한도.csv",
              ["관리번호", "적용월", "제품코드", "제품명", "최대생산수량", "단위", "집계기준", "사유"],
              [(cid, m, p, names[p], q, "팩", "완제품 생산량", "선물세트 박스 조립 외주 능력") for cid, p, m, q in QUANTITY_LIMITS])
    basis = {r[0]: r[3] for r in RESOURCES}
    expect(up / "08_capacity_hours_budgets.csv",
           ["capacity_id", "resource_id", "period", "regular_hours", "overtime_hours_limit", "unit", "time_basis",
            "availability_basis", "calendar_ref"],
           [(f"H-{r}", r, m, reg, ot, "h", basis[r], "NET", "") for r, by in HOURS.items() for m, (reg, ot) in by.items()])
    res_name = {r[0]: r[1] for r in RESOURCES}
    write_csv(raw / "plans" / "월별가용시간계획.csv",
              ["적용월", "설비코드", "설비명", "정규가용시간(h)", "잔업한도(h)", "산정기준", "비고"],
              [(m, r, res_name[r], HOURS[r][m][0], HOURS[r][m][1], "순가용시간(정비·휴식 제외)",
                "설 연휴(2/6~2/9)로 정규시간 감소" if m == "2027-02" else "") for m in PLAN_MONTHS for r in HOURS])
    write_csv(master_dir / "원가기준.csv", ["항목구분", "대상코드", "대상명", "정규단가", "잔업단가", "단위", "비고"],
              [("작업자" if basis[r] == "PERSON_HOUR" else "설비", r, res_name[r], reg, ot,
                "원/인시" if basis[r] == "PERSON_HOUR" else "원/설비시간", "잔업은 정규의 1.5배")
               for r, (reg, ot) in RESOURCE_COST.items()] +
              [("재고유지비율", "전 제품", "월 재고유지비(자재원가 대비)", dec(HOLDING_COST_RATE * 100), "", "%", "보관·자금비용 가정")])
    po_price = MATERIAL_COST[SCHEDULED_RECEIPTS[0][1]]
    write_csv(raw / "snapshots" / "미입고발주현황_20261231.csv",
              ["기준일", "발주번호", "발주일", "공급사코드", "공급사명", "자재코드", "자재명", "발주수량", "기입고수량",
               "미입고수량", "단위", "단가", "금액", "납기예정일"],
              [(AS_OF_DATE, po, "2026-12-28", sup, next(s[1] for s in masters.SUPPLIERS if s[0] == sup), mat,
                mat_name[mat], qty, 0, qty, unit, po_price, qty * po_price, due)
               for po, mat, qty, unit, due, sup in SCHEDULED_RECEIPTS])

    # ---- 라우팅 (entity=routing) ----
    routing_rows = []
    for code, steps in ROUTES.items():
        prev = None
        for step, res, ref, hrs in steps:
            extra = []
            if res in LABOR_PER_1000_PACKS:
                extra = [{"resource_id": "LB1", "reference_qty": "1000", "quantity_unit": "EA",
                          "run_time": str(LABOR_PER_1000_PACKS[res]), "time_unit": "h", "time_basis": "PERSON_HOUR",
                          "concurrent_units": None, "setup_time": None, "setup_policy_ref": None,
                          "alternative_group_ref": None}]
            routing_rows.append((res, ref, "EA", hrs, "h", "MACHINE_HOUR", "", "", "", "",
                                 f"RT-{code}", "V1", step, code, step, json.dumps([prev] if prev else []),
                                 "2022-01-01", "", json.dumps(extra, ensure_ascii=False)))
            prev = step
    expect(up / "09_routing_steps.csv",
           ["resource_id", "reference_qty", "quantity_unit", "run_time", "time_unit", "time_basis", "concurrent_units",
            "setup_time", "setup_policy_ref", "alternative_group_ref", "routing_id", "routing_version", "step_id",
            "product_id", "operation_id", "predecessor_step_ids", "valid_from", "valid_to", "resource_requirements"],
           routing_rows)
    write_csv(master_dir / "공정표.csv",
              ["제품코드", "제품명", "공정순서", "공정코드", "공정명", "설비코드", "설비명", "시간당처리량(팩)",
               "1000팩당작업인시", "작업자코드", "적용시작일"],
              [(code, names[code], (i + 1) * 10, step, OPERATION_NAME[step], res, res_name[res], ref,
                LABOR_PER_1000_PACKS.get(res, ""), "LB1" if res in LABOR_PER_1000_PACKS else "", "2022-01-01")
               for code, steps in ROUTES.items() for i, (step, res, ref, _) in enumerate(steps)])

    # ---- 분석용 집계(derived)의 기대값 ----
    cost_rows = []
    for r, (reg, ot) in RESOURCE_COST.items():
        unit = "PERSON_HOUR" if basis[r] == "PERSON_HOUR" else "MACHINE_HOUR"
        cost_rows += [("RESOURCE", r, "REGULAR", reg, 1, unit, "KRW"), ("RESOURCE", r, "OVERTIME", ot, 1, unit, "KRW")]
    product_cost = {}
    for code, lines in BOM.items():
        product_cost[code] = sum(Decimal(q) * (1 + Decimal(s)) * MATERIAL_COST[m] for m, q, _, s in lines)
        cost_rows.append(("PRODUCT", code, "HOLDING_PER_MONTH", dec(product_cost[code] * HOLDING_COST_RATE, 0), 1, "EA", "KRW"))
    expect(derived / "costs.csv", ["target_kind", "target_id", "cost_component", "amount", "per_quantity",
                                   "quantity_unit", "currency"], cost_rows)
    expect(derived / "scheduled_receipts.csv", ["po_id", "material_id", "qty", "unit", "expected_date", "supplier_id"],
           SCHEDULED_RECEIPTS)

    # ---- raw → upload/derived 변환 후, 기대값과 한 글자라도 다르면 멈춘다 ----
    monthly, _ = convert.convert_all(raw, up, derived)
    target = {(c, p): q for c, s in demand.items() for p, q in s if q > 0}
    if monthly != target:
        bad = sorted(set(monthly.items()) ^ set(target.items()))[:5]
        raise SystemExit(f"판매 내역 합계가 월 판매량과 다릅니다: {bad}")
    for path, text in expected.items():
        if path.read_bytes().decode("utf-8-sig") != text:      # 줄바꿈(\r\n)까지 그대로 비교
            raise SystemExit(f"raw에서 변환한 결과가 기대값과 다릅니다: {path.relative_to(OUT)}")

    # ---- 검증 테스트용 오류 파일 (정상 파일에서 일부만 망가뜨림) ----
    er = OUT / "errors"
    main_series = demand["CP-N3-3030"][-6:]
    write_csv(er / "demand_missing_qty.csv", ["product_id", "period", "demand_qty", "unit"],
              [("CP-N3-3030", p, "" if i == 2 else q, "EA") for i, (p, q) in enumerate(main_series)])
    write_csv(er / "demand_duplicate_period.csv", ["product_id", "period", "demand_qty", "unit"],
              [("CP-N3-3030", p, q, "EA") for p, q in main_series] + [("CP-N3-3030", *main_series[-1], "EA")])
    write_csv(er / "demand_bad_period_format.csv", ["product_id", "period", "demand_qty", "unit"],
              [("CP-N3-3030", p.replace("-", "/") if i == 0 else p, q, "EA") for i, (p, q) in enumerate(main_series)])
    write_csv(er / "products_unknown_unit.csv", ["제품코드", "제품명", "단위", "제품유형", "안전재고"],
              [("CP-N3-3030", "천연펄프 3겹 30m 30롤", "BOXX", "완제품", ss["CP-N3-3030"])])
    write_csv(er / "bom_unknown_material.csv", ["BOM코드", "제품코드", "버전", "상태", "활성", "유효시작일", "유효종료일",
                                                "기준수량", "순번", "구성유형", "구성품코드", "소요량", "단위", "스크랩률"],
              [("BOM-CP-N3-3030", "CP-N3-3030", "V1", "APPROVED", "Y", "2022-01-01", "", 1, 1, "MATERIAL", "MR-XXX",
                "4.05", "kg", "0.03")])
    write_csv(er / "inventory_negative_qty.csv", ["품목구분", "품목코드", "기준일", "현재고", "할당재고", "가용재고", "단위"],
              [("MATERIAL", "MR-N3", AS_OF_DATE, -100, 0, -100, "kg")])

    # ---- 사람이 읽는 요약 ----
    write_summary(demand, ma12, ss, fg_inv, need, mat_req, mat_inv, mat_ss, product_cost)


def verify_report_against_masters(order_rows, product_master, customer_master, price_book, bom_rows):
    """판매 내역 보고서와 BOM이 마스터와 어긋나면 멈춘다."""
    from datetime import date
    products = {r[0]: r for r in product_master}          # 코드 → 행 (이름 1, 출시일 11)
    customers = {r[0]: r for r in customer_master}        # 코드 → 행 (이름 1, 채널 2, 시작 5, 종료 6)
    problems = []
    for r in order_rows:
        d = date.fromisoformat(r[0])
        cust, prod = customers.get(r[4]), products.get(r[7])
        if cust is None or prod is None:
            problems.append(f"마스터에 없는 코드 {r[4]} / {r[7]}")
            continue
        if (r[5], r[6]) != (cust[1], cust[2]):
            problems.append(f"거래처명·채널 불일치 {r[2]}")
        if r[8] != prod[1]:
            problems.append(f"제품명 불일치 {r[2]}")
        if not (date.fromisoformat(cust[5]) <= d <= (date.fromisoformat(cust[6]) if cust[6] else date.max)):
            problems.append(f"거래 기간 밖 기록 {r[2]} {r[4]} {r[0]}")
        if d < date.fromisoformat(prod[11]):
            problems.append(f"출시 전 판매 {r[2]} {r[7]} {r[0]}")
        if r[11] != price_book.price(r[7], r[6], d if r[13] != "반품" else date.fromisoformat(
                "20" + r[14][3:5] + "-" + r[14][5:7] + "-" + r[14][7:9])):
            problems.append(f"단가표와 다른 단가 {r[2]}")
        if r[9] * r[11] != r[12]:
            problems.append(f"금액 계산 불일치 {r[2]}")
    for row in bom_rows:                                   # 원단 소요량 = 제품 규격 × 원단 평량
        if row[10].startswith("MR-") and Decimal(row[11]) != Decimal(dec(masters.paper_kg_per_pack(row[1]))):
            problems.append(f"BOM 원단량이 제품 규격과 다름 {row[1]}")
    if problems:
        raise SystemExit("마스터 검증 실패:\n" + "\n".join(problems[:20]))


def write_dirty_sample(order_rows, path: Path):
    """2026-03 판매 내역 200행에 실제 엑셀에서 흔한 문제를 섞는다. 섞은 종류와 개수는 README에 적는다."""
    rng = random.Random(SEED + 2)
    rows = [list(r) for r in order_rows if r[0].startswith("2026-03") and r[13] == "정상"][:200]
    for i, r in enumerate(rows):
        y, m, d = r[0].split("-")
        if i % 7 == 1:
            r[0] = f"{y}.{m}.{d}"
        elif i % 7 == 3:
            r[0] = f"{y}{m}{d}"
        elif i % 7 == 5:
            r[0] = f"{int(m)}/{int(d)}/{y}"
    for i in rng.sample(range(len(rows)), 5):
        rows[i][9] = f"{rows[i][9]}팩"
    for i in rng.sample(range(len(rows)), 3):
        rows[i][9] = ""
    for i in rng.sample(range(len(rows)), 3):
        rows[i][7] = ""
    for i in rng.sample(range(len(rows)), 3):
        rows[i][4] = f" {rows[i][4]} "
    for i in rng.sample(range(len(rows)), 5):
        rows.insert(i + 1, list(rows[i]))
    write_csv(path, sales_orders.HEADER, rows)


def write_summary(demand, ma12, ss, fg_inv, need, mat_req, mat_inv, mat_ss, product_cost):
    load = {r[0]: Decimal(0) for r in RESOURCES}
    for code, steps in ROUTES.items():
        for _, res, ref, hrs in steps:
            load[res] += Decimal(need[code]) * hrs / ref
            if res in LABOR_PER_1000_PACKS:
                load["LB1"] += Decimal(need[code]) * LABOR_PER_1000_PACKS[res] / 1000
    yearly = {}
    for c, s in demand.items():
        for p, q in s:
            yearly.setdefault(c, {}).setdefault(p[:4], 0)
            yearly[c][p[:4]] += q
    years = sorted({y for v in yearly.values() for y in v})
    lines = [f"# 생성 결과 요약 — {COMPANY}", "",
             f"SEED {SEED}. 아래 '어림' 값은 2027-01 예측 기본값(최근 12개월 평균, MA12)으로 계산한 설계 확인용이며 엔진 정답이 아니다.", "",
             "## 제품별 연간 판매량 (팩)", "", "| 제품 | " + " | ".join(years) + " | MA12 | 안전재고 | 기초재고 | 1월 생산 필요 어림 |",
             "|---|" + "---|" * (len(years) + 4)]
    for code, name, *_ in PRODUCTS:
        cells = [f"{yearly[code].get(y, 0):,}" if yearly[code].get(y) else "-" for y in years]
        lines.append(f"| {code} {name} | " + " | ".join(cells) +
                     f" | {ma12[code]:,.0f} | {ss[code]:,} | {fg_inv[code]:,} | {need[code]:,} |")
    lines += ["", "## 2027-01 설비·인력 부하 어림", "", "| 자원 | 부하 어림 (h) | 정규 | 잔업 한도 | 정규 대비 |", "|---|---|---|---|---|"]
    for r, *_ in RESOURCES:
        reg, ot = HOURS[r]["2027-01"]
        lines.append(f"| {r} | {float(load[r]):,.1f} | {reg} | {ot} | {float(load[r]) / reg:.0%} |")
    lines += ["", "## 2027-01 자재 소요 어림 vs 재고", "", "| 자재 | 소요 어림 | 안전재고 | 기초재고 | 여유 |", "|---|---|---|---|---|"]
    for m, _, u, _ in MATERIALS:
        slack = mat_inv[m] - mat_req[m] - mat_ss[m]
        lines.append(f"| {m} ({u}) | {float(mat_req[m]):,.1f} | {mat_ss[m]:,} | {mat_inv[m]:,} | {float(slack):,.1f} |")
    lines += ["", "## 제품 원가 (자재비만, 원/팩)", ""]
    lines += [f"- {c}: {float(v):,.0f}" for c, v in product_cost.items()]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
