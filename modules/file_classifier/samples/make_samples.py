"""문서 종류 분류용 실제 엑셀 더미 파일 생성기 v3 (SYNTHETIC). openpyxl 이 필요하다.

    python -X utf8 modules/file_classifier/samples/make_samples.py

산출물
    samples/inbox/*.xlsx     종류 구분 없이 섞인 엑셀 200개 (.gitignore 대상이라 저장소에는 올라가지 않는다)
    samples/labels.json      파일별 정답 범주, 표 형태, 형태의 출처

v1 은 "열 이름 한 줄 + 데이터"인 깔끔한 표뿐이라 실제 문서와 달랐다. v2 는 공개 자료에서 확인한 실제 표 형태를 본떴다.
수치와 회사(㈜충파모제지)는 모두 가정이며 실제 기업 자료가 아니다.
v3 는 v2 와 같은 200개(같은 파일명, 같은 표, 같은 정답)에 실제 사무실 엑셀의 겉모습과 흔적을 더했다: 문서 성격별 글꼴·머리글 색·테두리,
결재란, 문서번호, 날짜·숫자 서식, 합계 수식, 틀 고정·필터·인쇄 설정, 형광펜·메모·취소선·숨긴 열, 옆에 적어 둔 말, 빈 Sheet2·3, 지난 버전 사본,
숨긴 시트, 작성자 정보, "수 량"처럼 띄어 쓴 열 이름. 사람·거래처 이름도 실제처럼 바꿨다(모두 지어낸 이름이다).

표 형태의 출처 (labels.json 의 source). verified=True 는 공개 문서에서 열·행 이름을 글자로 확인한 것,
False 는 화면 캡처로만 공개되어 글자로 확인하지 못해 일반적으로 알려진 표기를 쓴 것이다.
    oracle-capacity   Oracle Capacity User's Guide 12.1, Rough Cut Capacity Planning 장의 예시 표 (verified)
                      https://docs.oracle.com/cd/E18727_01/doc.121/e15189/T473818T474769.htm
    oracle-mps        Oracle Master Scheduling/MRP 12.1 의 일정·예측 입력 표 (verified)
                      https://docs.oracle.com/cd/E18727-01/doc.121/b31558/T478564T478750.htm
    wikiversity-mps   Wikiversity "Master Production Schedule" 의 MPS Planning Analysis Table (verified)
                      https://en.wikiversity.org/wiki/Master_Production_Schedule
    cpim-mps          CPIM 학습 자료의 MPS 격자: Forecast / Customer orders / PAB / ATP / MPS (verified)
                      https://open-exam-prep.com/study-guides/cpim/master-scheduling/creating-master-schedule
    kurbel            Kurbel, "MRP: Material Requirements Planning" 교재 2장의 구조표·재고 구분·거래처 속성 (verified)
    kr-form           국내 서식 설명(생산일지, 주간 생산현황표, 불량품현황)과 ERP 블로그의 MRP 항목 (verified, 설명문 기준)
                      https://www.bizforms.co.kr/form_view/form_110214.asp , https://blog.iquest.co.kr (MRP·BOM 글)
    oee               설비종합효율 항목: 부하시간, 가동시간, 정지시간, 시간가동률, 성능가동률, 양품률 (verified, 용어)
    sap               SAP 표준 화면(CS12, MD04, CM01, 실적 조회). 공개 문서에는 화면 캡처뿐이라 열 이름은 미확인 (verified=False).
                      확인된 것: MD04 의 Date·MRP element 열, CM01 이 주 단위로 소요·가용능력·부하·잔여능력을 보여 준다는 점
    textbook          교재에 흔한 MRP 레코드 격자 (verified=False, 이번 검색에서 원문을 글자로 확인하지 못함)
    generic           출처 없이 만든 일반 목록 (ERP 거래·미분류 문서)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import random
import shutil

from openpyxl import Workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SEED = 20261117
HERE = pathlib.Path(__file__).resolve().parent
INBOX = HERE / "inbox"
PER_CATEGORY = 25
THIN = Side(style="thin")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

PRODUCTS = [(f"CP-{k}{ply}-{length}{rolls}", f"{pulp} {ply}겹 {length}m {rolls}롤") for k, pulp in (("N", "천연펄프"), ("R", "재생펄프"))
            for ply in (2, 3, 4) for length, rolls in ((30, 30), (27, 30), (25, 24), (30, 12))]
MATERIALS = [("MR-N2", "천연펄프 2겹 원단", "kg"), ("MR-N3", "천연펄프 3겹 원단", "kg"), ("MR-N4", "천연펄프 4겹 원단", "kg"),
             ("MR-R2", "재생펄프 2겹 원단", "kg"), ("MC-CORE", "지관", "EA"), ("MP-FILM30", "포장필름 30롤용", "EA"),
             ("MP-FILM24", "포장필름 24롤용", "EA"), ("MP-GIFTBOX", "선물세트 박스", "EA"), ("MP-OUTBOX", "외박스", "EA"), ("MP-LABEL", "라벨", "EA")]
RESOURCES = [("RW1", "되감기·엠보기 1호"), ("RW2", "되감기·엠보기 2호"), ("SAW1", "롤 절단기"), ("PK1", "포장기 1호"), ("PK2", "포장기 2호")]
WORK_CENTERS = ["1320-01", "1320-02", "1410-01", "1510-01"]
DEPTS = [("D1", "R1"), ("D1", "R2"), ("D2", "R1"), ("D3", "R1")]
CUSTOMERS = ["한빛마트 본사", "누리편의점", "온누리몰", "대성도매상사", "청풍호텔"]
SUPPLIERS = ["동방펄프상사", "한일원지공업", "성진지관산업", "우성포장"]
PEOPLE = ["김민수", "이서연", "박준형", "최은정", "정대호", "강미란"]


def q(rng, lo, hi, step=10):
    return rng.randrange(lo, hi, step)


def day(rng, year=2027, months=(1, 3)):
    return dt.date(year, rng.randint(*months), rng.randint(1, 28))


def kv(*pairs, per_row=3):
    return {"kind": "kv", "pairs": list(pairs), "per_row": per_row}


def table(headers, rows, groups=None, total=False):
    """groups: [(묶음 이름, 열 수), ...] 를 주면 열 이름 위에 병합된 묶음 줄을 하나 더 둔다."""
    return {"kind": "table", "headers": headers, "rows": rows, "groups": groups, "total": total}


def text(value):
    return {"kind": "text", "value": value}


def kr_form(rng, title, dept, blocks):
    """국내 수작업 서식 모양: 제목, 결재란, 작성일자·부서 줄을 붙인다."""
    top = [{"kind": "title", "value": title, "approval": rng.random() < 0.7},
           kv(("작성일자", day(rng, 2026, (11, 12))), ("부서", dept), ("작성자", rng.choice(PEOPLE)))]
    return top + blocks + ([text("※ 본 자료는 사내 검토용입니다.")] if rng.random() < 0.3 else [])


def weeks(rng, n, style):
    if style == "wk":
        return [f"WK {i}" for i in range(n)]
    if style == "week_num":
        return list(range(1, n + 1))
    if style == "sap":
        return [f"W {(34 + i) % 52 + 1:02d}/{2026 + (34 + i) // 52}" for i in range(n)]
    if style == "date":
        start = dt.date(2027, 1, 4)
        return [(start + dt.timedelta(days=7 * i)).strftime("%d-%b") for i in range(n)]
    return [f"Period {i}" for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------
def bom_structure_table(rng):
    rows = [[c, m[0], round(rng.uniform(0.5, 30), 2)] for c, _ in rng.sample(PRODUCTS, rng.randint(12, 24)) for m in rng.sample(MATERIALS, rng.randint(3, 5))]
    return [text("Structure"), table(["Upper-part-id", "Lower-part-id", "Quantity"], rows)], "kurbel", True


def bom_sap_multilevel(rng):
    blocks = []
    for c, n in rng.sample(PRODUCTS, rng.randint(3, 8)):
        blocks += _bom_sap_one(rng, c, n)
    return blocks, "sap", False


def _bom_sap_one(rng, c, n):
    rows, item = [], 10
    for m in rng.sample(MATERIALS, rng.randint(5, 9)):
        rows.append([".1", f"{item:04d}", "L", m[0], m[1], round(rng.uniform(0.5, 30), 3), m[2], ""])
        item += 10
        if rng.random() < 0.3:
            sub = rng.choice(MATERIALS)
            rows.append(["..2", "0010", "L", sub[0], sub[1], round(rng.uniform(0.1, 3), 3), sub[2], ""])
    return [kv(("Material", c), ("Plant", "1000"), ("Usage", "1"), ("Alternative", "01"), ("Description", n), ("Base Qty (EA)", 1)),
            table(["Level", "Item", "ICt", "Component number", "Object description", "Comp. Qty (CUn)", "Un", "Asm"], rows)]


def bom_kr_form(rng):
    name, code, usage, loss = rng.choice([("자재명", "품목번호", "소요량", "LOSS율(%)"), ("품명", "자품목코드", "정미수량", "로스율"),
                                          ("자품목명", "자품번", "필요수량", "손실률(%)")])
    blocks = []
    for c, n in rng.sample(PRODUCTS, rng.randint(3, 8)):
        blocks += _bom_kr_one(rng, c, n, name, code, usage, loss)
    return kr_form(rng, rng.choice(["자재명세서", "BOM 등록 내역", "제품 구성표"]), "생산관리팀", blocks), "kr-form", True


def _bom_kr_one(rng, c, n, name, code, usage, loss):
    rows = [[i, m[0], m[1], rng.choice(["2.7m 폭", "Ø38", "-", "0.03T"]), m[2], round(rng.uniform(0.5, 30), 2), rng.choice([0, 1, 2, 3]),
             rng.choice(["국내", "수입"]), q(rng, 20, 2000), ""] for i, m in enumerate(rng.sample(MATERIALS, rng.randint(5, 9)), 1)]
    return [kv(("모품목", c), ("품명", n), ("기준수량", "1 EA")),
            table(["No", code, name, "규격", "단위", usage, loss, "원산지", "단가", "비고"], rows)]


# ---------------------------------------------------------------------------
# MPS
# ---------------------------------------------------------------------------
def mps_wikiversity(rng):
    blocks = []
    cols = weeks(rng, 11, "wk")
    for c, _ in rng.sample(PRODUCTS, rng.randint(4, 9)):
        labels = ["Demand forecast", "Allocated", "Reserved", "Unplanned", "Net demand", "Firm Planned Order", "Planned Order", "PAB", "ATP"]
        rows = [[lab] + [("" if rng.random() < 0.2 else q(rng, 0, 60, 5)) for _ in cols] for lab in labels]
        blocks += [text(f"Product {c}"), table([f"Safety stock: {rng.choice([20, 40, 100])}"] + cols, rows)]
    return blocks, "wikiversity-mps", True


def mps_cpim(rng):
    blocks = []
    for c, n in rng.sample(PRODUCTS, rng.randint(4, 9)):
        blocks += _mps_cpim_one(rng, c, n)
    return blocks, "cpim-mps", True


def _mps_cpim_one(rng, c, n):
    cols = weeks(rng, 8, "week_num")
    labels = ["Forecast", "Customer orders", "Projected available balance (PAB)", "Available-to-promise (ATP)", "Master production schedule (MPS)"]
    rows = [[lab] + [q(rng, 0, 120, 5) for _ in cols] for lab in labels]
    return [kv(("Item", c), ("Description", n)), kv(("On hand", 120), ("Lot size", 100), ("Safety stock", 40)), table(["Week"] + cols, rows)]


def mps_oracle_entries(rng):
    rows = []
    for c, _ in rng.sample(PRODUCTS, rng.randint(10, 20)):
        for _ in range(rng.randint(3, 8)):
            d = day(rng)
            qty = q(rng, 500, 9000, 100)
            rows.append([c, d, d + dt.timedelta(days=4), qty, qty // 5])
    return [kv(("Master Schedule", "MPS-2027Q1"), ("Organization", "M1")),
            table(["Item", "Schedule Date", "Rate End Date", "Quantity", "Daily Quantity"], rows)], "oracle-mps", True


def mps_kr_weekly(rng):
    start = dt.date(2027, 1, 4)
    days = [(start + dt.timedelta(days=i)).strftime("%m/%d") for i in range(6)]
    rows = [[i, c, n, "EA"] + [q(rng, 0, 3000, 100) for _ in days] + [0, ""] for i, (c, n) in enumerate(rng.sample(PRODUCTS, rng.randint(14, 24)), 1)]
    for r in rows:
        r[10] = sum(r[4:10])
    title = rng.choice(["주간 생산계획표", "생산계획(안)", "주간 생산일정"])
    blocks = [table(["No", "품번", "품명", "단위"] + days + ["계", "비고"], rows, groups=[("", 4), ("일자별 계획수량", 6), ("", 2)], total=True)]
    return kr_form(rng, title, "생산관리팀", blocks), "kr-form", False


# ---------------------------------------------------------------------------
# MRP
# ---------------------------------------------------------------------------
def mrp_textbook_records(rng):
    blocks = []
    cols = weeks(rng, 8, rng.choice(["period", "week_num"]))
    for m in rng.sample(MATERIALS, rng.randint(6, 10)):
        labels = ["Gross Requirements", "Scheduled Receipts", "Projected On Hand", "Net Requirements", "Planned Order Receipts", "Planned Order Releases"]
        rows = [[lab] + [q(rng, 0, 9000, 100) for _ in cols] for lab in labels]
        blocks += [kv(("Item", m[0]), ("Low-Level Code", rng.choice([1, 2])), ("Lot Size", rng.choice([1000, 5000])), ("LT", rng.choice([1, 2, 3])),
                      ("On Hand", q(rng, 0, 9000, 100)), ("Safety Stock", q(rng, 0, 2000, 100)), per_row=6),
                   table([rng.choice(["Period", "Week"])] + cols, rows)]
    return blocks, "textbook", False


def mrp_sap_md04(rng):
    m = rng.choice(MATERIALS)
    rows, avail, d = [], q(rng, 1000, 9000, 100), dt.date(2026, 12, 28)
    rows.append([d, "Stock", "", "", "", "", avail])
    rows.append([d, "SafeSt", "Safety stock", "", "", -500, avail - 500])
    for _ in range(rng.randint(30, 70)):
        d += dt.timedelta(days=rng.randint(1, 4))
        kind = rng.choice(["DepReq", "PlOrd", "PurRqs", "SchLne", "POitem", "OrdRes"])
        qty = q(rng, 500, 6000, 100) * (-1 if kind in ("DepReq", "OrdRes") else 1)
        avail += qty
        rows.append([d, kind, f"{rng.randint(10000000, 49999999)}/{rng.choice(['STCK', 'NB', '000010'])}", "", rng.choice(["", "", "10", "15", "07"]), qty, avail])
    return [kv(("Material", m[0]), ("Plant", "1000"), ("MRP area", "1000"), ("Description", m[1]), ("MRP type", "PD"), ("Base Unit", m[2])),
            table(["Date", "MRP element", "MRP element data", "Rescheduling date", "Exception", "Receipt/Reqmt", "Available qty"], rows)], "sap", False


def mrp_kr_form(rng):
    rows = []
    for i, m in enumerate([rng.choice(MATERIALS) for _ in range(rng.randint(15, 40))], 1):
        gross, stock, safety, alloc, open_po = q(rng, 1000, 30000, 100), q(rng, 0, 9000, 100), q(rng, 0, 2000, 100), q(rng, 0, 1000, 100), q(rng, 0, 5000, 500)
        rows.append([i, m[0], m[1], m[2], gross, stock, safety, alloc, open_po, max(gross - stock - open_po + safety + alloc, 0), rng.choice([7, 14, 21]),
                     rng.choice([5000, 10000])])
    heads = rng.choice([["No", "품목번호", "품목명", "단위", "총 소요량", "현 보유재고", "안전재고", "재고 할당량", "기발주주문량", "순 소요량", "리드타임", "발주량"],
                        ["순번", "품번", "품명", "단위", "총소요량", "현재고", "안전재고", "할당량", "기발주량", "순소요량", "L/T(일)", "발주예정량"]])
    title = rng.choice(["자재 소요량 산출표", "소요량 전개 결과", "자재소요계획"])
    return kr_form(rng, title, "구매팀", [kv(("계획기간", "2027-01 ~ 2027-03")), table(heads, rows)]), "kr-form", True


# ---------------------------------------------------------------------------
# RCCP
# ---------------------------------------------------------------------------
def rccp_oracle_load_ratio(rng):
    dept, res = rng.choice(DEPTS)
    rows = []
    for w in weeks(rng, rng.randint(13, 26), "date"):
        need, avail = 70 + q(rng, 80, 520, 20) // 4, rng.choice([140, 160])
        rows.append([w, need, avail, f"{round(need / avail * 100)}%"])
    return [text(f"Capacity Load Ratio for {dept}, {res}"), table(["Week Start Date", "Required Hours", "Available Hours", "Load Ratio"], rows)], "oracle-capacity", True


def rccp_oracle_bucketed(rng):
    rows = [[w, d, r, q(rng, 40, 520, 20)] for w in weeks(rng, rng.randint(10, 20), "date") for d, r in DEPTS]
    return [kv(("Master Schedule", "MPS-2027Q1"), ("Bill of Resources", "BOR-STD"), ("Cutoff Date", dt.date(2027, 3, 31))),
            table(["Week Start Date", "Department", "Resource", "Required Hours"], rows)], "oracle-capacity", True


def rccp_oracle_bill_of_resources(rng):
    rows = []
    for c, _ in rng.sample(PRODUCTS, rng.randint(12, 24)):
        for op, (d, r) in zip((10, 20, 30), rng.sample(DEPTS, 3)):
            hrs, qty = rng.choice([1, 2, 4, 6]), 1
            rows.append([c, op, d, r, rng.choice([0, 1, 2]), hrs, qty, rng.choice(["Item", "Lot"]), hrs * qty, c])
    return [text("Bills of Resources"),
            table(["Item", "Op Seq", "Dept", "Res", "Set Back Days", "Reqd Hrs", "Usage Qty", "Basis", "Total Hrs", "Source Item"], rows)], "oracle-capacity", True


def rccp_oracle_required_hours(rng):
    dept, res = rng.choice(DEPTS)
    rows = []
    for _ in range(rng.randint(25, 60)):
        d = day(rng)
        qty = q(rng, 10, 200, 10)
        rows.append([rng.choice(PRODUCTS)[0], d, qty, qty * rng.choice([2, 4, 6]), d - dt.timedelta(days=rng.choice([0, 1, 2]))])
    return [text(f"Required Hours and Required Dates for {dept}, {res}"),
            table(["Item", "Master Schedule Date", "Master Schedule Qty", "Required Hours", "Required Date"], rows)], "oracle-capacity", True


def rccp_kr_form(rng):
    months = [f"{i}월" for i in range(1, rng.choice([4, 7]))]
    need, have, rate = rng.choice([("소요공수", "보유공수", "부하율(%)"), ("필요시간", "가용시간", "부하율"), ("소요능력", "보유능력", "부하율(%)")])
    rows = []
    for r in RESOURCES:
        for lab in (need, have, rate):
            rows.append([r[1], lab] + [q(rng, 80, 220, 5) for _ in months])
        need_row, have_row, rate_row = rows[-3], rows[-2], rows[-1]
        have_row[2:] = [160 + have_row[2] // 20 * 5] * len(months)
        rate_row[2:] = [round(n / h * 100) for n, h in zip(need_row[2:], have_row[2:])]
    title = rng.choice(["주요 설비 부하 검토", "개략 능력 검토(월)", "설비별 공수 검토"])
    return kr_form(rng, title, "생산관리팀", [kv(("기준", "MPS 2027년 1분기")), table(["설비", "구분"] + months, rows)]), "kr-form", False


# ---------------------------------------------------------------------------
# CRP
# ---------------------------------------------------------------------------
def crp_sap_cm01(rng):
    blocks = [text("Capacity Planning: Standard Overview")]
    for wc in rng.sample(WORK_CENTERS, rng.randint(2, 4)):
        blocks += _crp_cm01_one(rng, wc)
    return blocks, "sap", False


def _crp_cm01_one(rng, wc):
    rows = []
    for w in weeks(rng, rng.randint(12, 20), "sap"):
        req, avail = round(rng.uniform(10, 120), 2), 80.0
        rows.append([w, req, avail, f"{round(req / avail * 100)} %", round(avail - req, 2), "H"])
    return [kv(("Work center", wc), ("Plant", "1000"), ("Capacity cat.", "001")),
            table(["Week", "Requirements", "AvailCap.", "CapLoad", "RemAvailCap", "Unit"], rows, total=True)]


def crp_sap_details(rng):
    wc = rng.choice(WORK_CENTERS)
    rows = []
    for _ in range(rng.randint(30, 80)):
        s = day(rng)
        rows.append([rng.choice(["Planned order", "Production order"]), f"{rng.randint(1000000, 1999999)}", rng.choice(PRODUCTS)[0], f"{rng.choice([10, 20, 30]):04d}",
                     round(rng.uniform(0.2, 1.5), 2), round(rng.uniform(1, 12), 2), s, s + dt.timedelta(days=rng.randint(0, 3)), "H"])
    return [text("Capacity Planning: Standard Overview: Details"), kv(("Work center", wc), ("Plant", "1000"), ("Week", "W 36/2026")),
            table(["Category", "Order", "Material", "Operation", "Setup reqmts", "Proc. reqmts", "Earl. start", "Latest finish", "Unit"], rows)], "sap", False


def crp_kr_form(rng):
    rows = []
    for i in range(1, rng.randint(30, 80)):
        setup, run = round(rng.uniform(0.2, 1.5), 1), round(rng.uniform(1, 12), 1)
        rows.append([i, rng.choice(["되감기", "절단", "포장"]), f"WO-{rng.randint(270000, 279999)}", rng.choice(PRODUCTS)[0], rng.choice([10, 20, 30]), setup, run,
                     round(setup + run, 1), day(rng), day(rng)])
    heads = rng.choice([["No", "작업장", "작업지시번호", "품번", "공정순서", "준비시간", "가공시간", "부하시간", "착수예정일", "완료예정일"],
                        ["순번", "공정", "제조오더", "품번", "공정번호", "셋업(h)", "작업(h)", "소요공수", "시작일", "종료일"]])
    title = rng.choice(["공정별 부하 현황", "작업장 부하 상세", "능력소요계획"])
    return kr_form(rng, title, "생산관리팀", [kv(("대상기간", "2027-01-04 ~ 2027-01-31")), table(heads, rows)]), "kr-form", False


# ---------------------------------------------------------------------------
# MES
# ---------------------------------------------------------------------------
def mes_kr_daily_log(rng):
    rows = []
    for _ in range(rng.randint(18, 45)):
        c, n = rng.choice(PRODUCTS)
        rows.append([f"{rng.randint(8, 16):02d}:00~{rng.randint(17, 19):02d}:00", n, c[-4:], q(rng, 500, 5000, 100), rng.choice(["되감기", "절단", "포장"]), rng.choice(PEOPLE),
                     rng.choice(["실시", "생략"]), rng.choice(["외관", "길이", "중량"]), rng.choice(["합격", "합격", "불합격"])])
    return kr_form(rng, rng.choice(["생산일지", "작업일보", "생산일보"]), "생산1팀",
                   [table(["작업시간", "품명", "규격", "수량", "공정명", "작업자", "품질공정검사", "검사내용", "결과"], rows, total=True)]), "kr-form", True


def mes_kr_weekly_status(rng):
    rows = []
    for i, d in enumerate(["월", "화", "수", "목", "금", "토"], 1):
        good, bad = q(rng, 2000, 9000, 100), rng.randint(0, 120)
        rows.append([i, d, rng.randint(4, 9), good, bad, f"{bad / (good + bad) * 100:.2f}%", rng.choice(["엠보 불량", "절단 불량", "포장 터짐", "-"]), rng.choice(PEOPLE)])
    return kr_form(rng, "주간 생산현황표", "생산1팀",
                   [table(["순번", "주간", "작업인원", "정품수량", "불량수량", "불량률", "불량원인", "책임자"], rows, total=True)]), "kr-form", True


def mes_kr_defects(rng):
    rows = []
    for mth in range(1, rng.randint(7, 13)):
        made, bad = q(rng, 50000, 200000, 1000), rng.randint(100, 3000)
        rows.append([f"{mth}월", made, bad, f"{bad / made * 100:.2f}%", rng.choice(PRODUCTS)[1], rng.choice(["엠보 불량", "절단 불량", "이물"]), rng.choice(["금형 교체", "작업자 교육", "점검 주기 단축"])])
    return kr_form(rng, "불량품현황(불량사유포함)", "품질팀", [table(["월", "생산량", "불량수량", "불량율", "제품명", "불량사유", "개선대책"], rows, total=True)]), "kr-form", True


def mes_oee(rng):
    rows = []
    for r in RESOURCES:
        load, stop = 480, rng.randint(10, 120)
        rows.append([r[0], r[1], load, load - stop, stop, f"{(load - stop) / load * 100:.1f}%", f"{rng.uniform(80, 99):.1f}%", f"{rng.uniform(95, 99.9):.1f}%",
                     f"{rng.uniform(60, 92):.1f}%"])
    return kr_form(rng, rng.choice(["설비가동일보", "설비종합효율 현황"]), "설비팀",
                   [table(["설비코드", "설비명", "부하시간", "가동시간", "정지시간", "시간가동률", "성능가동률", "양품률", "설비종합효율"], rows,
                          groups=[("", 2), ("시간(분)", 3), ("효율", 4)])]), "oee", True


def mes_sap_confirmations(rng):
    rows = []
    for _ in range(rng.randint(40, 120)):
        qty, scrap = q(rng, 500, 5000, 100), rng.randint(0, 40)
        rows.append([f"{rng.randint(1000000, 1999999)}", f"{rng.choice([10, 20, 30]):04d}", rng.choice(PRODUCTS)[0], rng.choice(WORK_CENTERS), qty - scrap, scrap, "EA",
                     day(rng, 2026, (10, 12)), rng.choice(PEOPLE)])
    return [kv(("Plant", "1000"), ("Order Type", "PP01")),
            table(["Order", "Activity", "Material", "Work center", "Yield", "Scrap", "Unit", "Posting date", "Entered by"], rows)], "sap", False


# ---------------------------------------------------------------------------
# ERP (기준정보·거래)
# ---------------------------------------------------------------------------
def erp_stock_kurbel(rng):
    rows = [[c, q(rng, 0, 90000, 50), q(rng, 0, 900, 50), q(rng, 0, 900, 50), q(rng, 0, 9000, 500), q(rng, 500, 5000, 500), q(rng, 100, 2000, 100)]
            for c in [p[0] for p in rng.sample(PRODUCTS, 8)] + [m[0] for m in MATERIALS]]
    return [table(["Part", "Physical inventory", "Shop-floor stock", "Reserved stock", "Open order quantity", "Reorder level", "Safety stock"], rows)], "kurbel", True


def erp_supplier_kurbel(rng):
    rows = [[f"S{1000 + i}", s, rng.choice(["충북 청주시", "경기 안산시", "부산 사상구"]), rng.choice(PEOPLE), rng.choice(["Net 30", "Net 45", "Net 60"]),
             rng.choice(["A", "B", "C"]), q(rng, 10000000, 90000000, 1000000)] for i, s in enumerate([f"{rng.choice(SUPPLIERS)} {k}지점" for k in range(1, rng.randint(15, 35))])]
    return [table(["Supplier number", "Supplier name", "Address", "Contact person", "Payment data", "Supplier rating", "Liability limit"], rows)], "kurbel", True


def erp_customer_kurbel(rng):
    rows = [[f"C{2000 + i}", c, rng.choice(["서울 강남구", "경기 성남시", "대전 유성구"]), rng.choice(PEOPLE), rng.choice(["A", "B"]), q(rng, 10000000, 90000000, 1000000)]
            for i, c in enumerate([f"{rng.choice(CUSTOMERS)} {k}호점" for k in range(1, rng.randint(20, 60))])]
    return [table(["Customer number", "Customer name", "Address", "Contact person", "Customer rating", "Credit line"], rows)], "kurbel", True


def erp_kr_list(headers, row_fn, title, name):
    def build(rng):
        rows = [[i] + row_fn(rng) for i in range(1, rng.randint(40, 150))]
        blocks = [kv(("조회기간", "2026-10-01 ~ 2026-12-31"), ("사업장", "본사")), table(["No"] + headers, rows, total=rng.random() < 0.4),
                  text(f"출력일시: 2026-12-{rng.randint(20, 30)} 09:{rng.randint(10, 59)}")]
        return ([{"kind": "title", "value": title, "approval": False}] + blocks), "generic", False
    build.__name__ = name
    return build


def _sales(rng):
    c, n = rng.choice(PRODUCTS)
    qty, price = q(rng, 10, 600), q(rng, 6000, 14000, 100)
    return [day(rng, 2026, (10, 12)), f"SO{rng.randint(261000, 269999)}", rng.choice(CUSTOMERS), c, n, qty, price, qty * price, int(qty * price * 0.1), day(rng)]


def _po(rng):
    m, qty, price = rng.choice(MATERIALS), q(rng, 1000, 20000, 500), rng.choice([25, 100, 120, 600, 1100, 1800])
    return [day(rng, 2026, (10, 12)), f"PO{rng.randint(261000, 269999)}", rng.choice(SUPPLIERS), m[0], m[1], m[2], qty, price, qty * price, day(rng), rng.choice(["발주", "입고완료"])]


def _item(rng):
    if rng.random() < 0.5:
        c, n = rng.choice(PRODUCTS)
        return [c, n, "30롤", "제품", "EA", "생산", q(rng, 300, 1000, 100), "Y"]
    m = rng.choice(MATERIALS)
    return [m[0], m[1], "-", rng.choice(["원재료", "부재료"]), m[2], "구매", q(rng, 100, 5000, 100), "Y"]


def _stock(rng):
    m = rng.choice(MATERIALS)
    a, b, c = q(rng, 0, 9000, 100), q(rng, 0, 20000, 500), q(rng, 0, 20000, 500)
    return [rng.choice(["원자재창고", "제품창고"]), m[0], m[1], m[2], a, b, c, a + b - c]


def _price(rng):
    return [rng.choice(PRODUCTS)[0], rng.choice(CUSTOMERS), q(rng, 6000, 14000, 100), "KRW", dt.date(2026, 3, 1), ""]


ERP_KR = [
    erp_kr_list(["수주일자", "수주번호", "거래처", "품번", "품명", "수량", "단가", "공급가액", "부가세", "납기일"], _sales, "수주현황", "erp_kr_sales"),
    erp_kr_list(["발주일자", "발주번호", "거래처", "품번", "품명", "단위", "수량", "단가", "금액", "납기일", "진행"], _po, "발주현황", "erp_kr_po"),
    erp_kr_list(["품번", "품명", "규격", "계정구분", "재고단위", "조달구분", "안전재고량", "사용여부"], _item, "품목등록 현황", "erp_kr_item"),
    erp_kr_list(["창고", "품번", "품명", "단위", "기초수량", "입고수량", "출고수량", "재고수량"], _stock, "재고수불부", "erp_kr_stock"),
    erp_kr_list(["품번", "거래처", "단가", "통화", "적용시작일", "적용종료일"], _price, "거래처별 단가 현황", "erp_kr_price"),
]


# ---------------------------------------------------------------------------
# 미분류
# ---------------------------------------------------------------------------
def etc(headers, row_fn, title, name):
    def build(rng):
        rows = [row_fn(rng) for _ in range(rng.randint(20, 80))]
        blocks = [table(headers, rows)]
        return (kr_form(rng, title, "총무팀", blocks) if rng.random() < 0.6 else blocks), "generic", False
    build.__name__ = name
    return build


ETC = [
    etc(["사번", "성명", "부서", "직급", "입사일", "재직상태"], lambda r: [f"E{r.randint(1000, 9999)}", r.choice(PEOPLE), r.choice(["생산팀", "품질팀"]), r.choice(["사원", "대리"]), day(r, 2019, (1, 12)), "재직"], "사원명부", "etc_hr"),
    etc(["근무일", "사번", "성명", "출근", "퇴근", "연장근로(h)"], lambda r: [day(r, 2026, (10, 12)), f"E{r.randint(1000, 9999)}", r.choice(PEOPLE), "08:55", "18:05", r.choice([0, 1, 2])], "근태 기록", "etc_attendance"),
    etc(["번호", "안건", "결정사항", "담당", "기한"], lambda r: [r.randint(1, 30), r.choice(["안전교육 일정", "휴게실 보수", "워크숍 장소"]), r.choice(["승인", "보류"]), r.choice(PEOPLE), day(r)], "회의록", "etc_minutes"),
    etc(["응답번호", "연령대", "성별", "만족도", "재구매의향", "의견"], lambda r: [r.randint(1, 500), r.choice(["20대", "30대"]), r.choice(["남", "여"]), r.randint(1, 5), r.randint(1, 5), r.choice(["부드러움", "가격"])], "고객 설문 결과", "etc_survey"),
    etc(["과정명", "교육일", "강사", "대상", "시간(h)", "장소"], lambda r: [r.choice(["산업안전", "소방훈련", "개인정보 보호"]), day(r), r.choice(PEOPLE), "전 직원", r.choice([1, 2, 4]), "대회의실"], "교육 일정", "etc_training"),
    etc(["운행일", "차량번호", "운전자", "목적지", "주행거리(km)", "주유량(L)"], lambda r: [day(r, 2026, (10, 12)), f"{r.randint(10, 99)}가{r.randint(1000, 9999)}", r.choice(PEOPLE), r.choice(["청주", "서울"]), r.randint(40, 420), r.randint(5, 60)], "차량 운행일지", "etc_vehicle"),
    etc(["월", "에너지원", "사용량", "단위", "요금(원)"], lambda r: [f"2026-{r.randint(1, 12):02d}", r.choice(["전기", "가스", "용수"]), q(r, 1000, 90000, 100), r.choice(["kWh", "Nm3"]), q(r, 100000, 9000000, 1000)], "에너지 사용 현황", "etc_energy"),
    etc(["부서", "성명", "휴대전화", "내선", "비상시 역할"], lambda r: [r.choice(["생산팀", "총무팀"]), r.choice(PEOPLE), "010-0000-0000", r.randint(100, 399), r.choice(["대피 유도", "초기 소화"])], "비상연락망", "etc_contacts"),
    etc(["점검일", "점검구역", "점검항목", "결과", "점검자", "조치사항"], lambda r: [day(r, 2026, (10, 12)), r.choice(["창고", "사무동"]), r.choice(["소화기", "비상구", "조명"]), r.choice(["양호", "보완"]), r.choice(PEOPLE), "-"], "안전점검표", "etc_safety"),
    etc(["신청일", "신청자", "물품명", "개수", "용도", "승인"], lambda r: [day(r, 2026, (10, 12)), r.choice(PEOPLE), r.choice(["A4 용지", "토너", "볼펜"]), r.randint(1, 20), "사무용", r.choice(["Y", "N"])], "사무용품 신청서", "etc_supplies"),
]

TEMPLATES = {
    "BOM": [bom_structure_table, bom_sap_multilevel, bom_kr_form],
    "MPS": [mps_wikiversity, mps_cpim, mps_oracle_entries, mps_kr_weekly],
    "MRP": [mrp_textbook_records, mrp_sap_md04, mrp_kr_form],
    "RCCP": [rccp_oracle_load_ratio, rccp_oracle_bucketed, rccp_oracle_bill_of_resources, rccp_oracle_required_hours, rccp_kr_form],
    "CRP": [crp_sap_cm01, crp_sap_details, crp_kr_form],
    "MES": [mes_kr_daily_log, mes_kr_weekly_status, mes_kr_defects, mes_oee, mes_sap_confirmations],
    "ERP": [erp_stock_kurbel, erp_supplier_kurbel, erp_customer_kurbel] + ERP_KR,
    "미분류": ETC,
}
FILE_HINTS = {"BOM": ["BOM", "자재명세서"], "MPS": ["MPS", "생산계획"], "MRP": ["MRP", "자재소요"], "RCCP": ["RCCP", "설비부하검토"], "CRP": ["CRP", "작업장부하"],
              "MES": ["MES", "생산일보", "가동현황"], "ERP": ["ERP", "조회"], "미분류": ["자료", "대장"]}
NEUTRAL_FILES = ["Book1", "새 Microsoft Excel 워크시트", "첨부", "자료", "export", "download", "최종", "수정본", "검토", "data", "보고", "Sheet", "EXPORT", "report"]


# ---------------------------------------------------------------------------
# 파일 쓰기 (v3: 실제 사무실 엑셀처럼 보이게 하는 서식·흔적)
# ---------------------------------------------------------------------------
YELLOW = PatternFill("solid", fgColor="FFFF00")
SPACED = {"수량": "수 량", "품명": "품 명", "단위": "단 위", "비고": "비 고", "규격": "규 격", "결과": "결 과", "단가": "단 가", "금액": "금 액"}
MEMOS = ["확인 필요", "수량 재확인 바랍니다", "전월 대비 증가", "단가 변경 반영", "1/15 회의 후 수정", "구매팀 회신 대기", "잠정치"]
SIDE_NOTES = ["※ 1/20 수정", "→ 담당자 확인 중", "※ 잠정치", "※ 전월 이월분 포함", "※ 회의 후 재작성 예정"]
APPROVAL_ROLES = [["담당", "팀장", "공장장"], ["작성", "검토", "승인"], ["담당", "과장", "부장", "대표"]]


def profile_of(blocks, source):
    """표 형태의 출처에 따라 문서의 겉모습을 정한다: 수작업 서식 / 국내 ERP 조회 화면 내보내기 / SAP 내보내기 / 담당자 계획표."""
    has_title = any(b["kind"] == "title" for b in blocks)
    is_form = any(b["kind"] == "kv" and b["pairs"] and b["pairs"][0][0] == "작성일자" for b in blocks)
    if is_form:
        return "form"
    if source == "sap":
        return "sap"
    return "erp" if has_title else "planner"


def make_style(srng, profile):
    def side(style, color="000000"):
        return Side(style=style, color=color)

    if profile == "form":
        name, size = srng.choice([("맑은 고딕", 10), ("맑은 고딕", 11), ("굴림", 10), ("돋움", 10), ("바탕", 10)])
        st = {"head_fill": srng.choice(["D9D9D9", "F2F2F2", "FFF2CC", "DDEBF7", "E2EFDA"]), "head_font": "000000", "line": side("thin"), "borders": True,
              "title_size": srng.choice([16, 18, 20]), "title_align": "center", "grid": srng.random() < 0.4, "band": None}
    elif profile == "erp":
        name, size = srng.choice([("굴림체", 9), ("돋움", 9), ("맑은 고딕", 9), ("맑은 고딕", 10)])
        st = {"head_fill": srng.choice(["C0C0C0", "D9E1F2", "FFFFCC", "E7E6E6"]), "head_font": "000000", "line": side(srng.choice(["thin", "hair"])), "borders": True,
              "title_size": srng.choice([12, 14]), "title_align": "left", "grid": True, "band": None}
    elif profile == "sap":
        name, size = srng.choice([("Arial", 10), ("Calibri", 11), ("Arial", 9)])
        st = {"head_fill": srng.choice(["DBE5F1", "FFFF99", None]), "head_font": "000000", "line": side("thin", "BFBFBF"), "borders": srng.random() < 0.4,
              "title_size": size + 1, "title_align": "left", "grid": True, "band": None}
    else:
        name, size = srng.choice([("Calibri", 11), ("Arial", 10), ("맑은 고딕", 10)])
        fill, font = srng.choice([("1F4E78", "FFFFFF"), ("4472C4", "FFFFFF"), ("D9D9D9", "000000"), ("FCE4D6", "000000"), ("E2EFDA", "000000")])
        st = {"head_fill": fill, "head_font": font, "line": side("thin", srng.choice(["BFBFBF", "808080", "000000"])), "borders": srng.random() < 0.8,
              "title_size": srng.choice([12, 14]), "title_align": "left", "grid": True, "band": srng.choice([None, None, "F2F2F2", "EAF1FB"])}
    st.update(profile=profile, font=name, size=size, date_fmt=srng.choice(["yyyy-mm-dd", "yyyy-mm-dd", "yyyy.mm.dd", "yyyy/mm/dd", "m/d", "yy.mm.dd"]),
              date_text=profile in ("erp", "sap") and srng.random() < 0.3, formula=srng.random() < 0.3, spaced=profile == "form" and srng.random() < 0.15,
              roles=srng.choice(APPROVAL_ROLES), neg_red=profile == "planner" and srng.random() < 0.5)
    st["box"] = Border(left=st["line"], right=st["line"], top=st["line"], bottom=st["line"])
    return st


def _font(st, **kw):
    return Font(name=st["font"], size=kw.pop("size", st["size"]), **kw)


SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오"]
GIVEN = ["민수", "서연", "준형", "은정", "대호", "미란", "지훈", "수빈", "영호", "현주", "성민", "혜진"]


def _value(v, st, srng, n=None):
    if isinstance(v, dt.date) and st["date_text"]:
        return v.strftime("%Y.%m.%d")
    if n is not None and isinstance(v, str) and v in PEOPLE:      # 표 안의 사람 이름은 여섯 명만 되풀이되지 않게 넓힌다
        i = PEOPLE.index(v)
        return SURNAMES[(i + n) % 12] + GIVEN[(i * 5 + n * 7) % 12]
    if v == "010-0000-0000":
        return f"010-{srng.randint(2000, 9899)}-{srng.randint(1000, 9999)}"
    return v


def write_blocks(ws, rng, srng, blocks, offset, st):
    """rng 는 v2 와 같은 순서로만 쓴다(배치가 v2 와 같게 유지된다). 새로 더한 꾸밈은 모두 srng 로 정한다."""
    r, c0 = 1 + rng.choice([0, 0, 1]), 1 + offset
    tables, joined_file, table_cells = [], None, set()
    col_width: dict[int, float] = {}
    for b in blocks:
        if b["kind"] == "table":
            for j, h in enumerate(b["headers"]):
                widest = max([_width(h)] + [_width(x[j]) for x in b["rows"] if j < len(x) and x[j] is not None])
                col_width[c0 + j] = max(col_width.get(c0 + j, 0), min(max(widest + 2.5, 6), 42))

    def skip(col, need):
        """need 만큼의 글자 폭이 들어갈 때까지 오른쪽으로 건너뛴 다음 열 번호."""
        used = 0.0
        while used < need:
            used += col_width.get(col, 10)
            col += 1
        return col

    for block in blocks:
        kind = block["kind"]
        if kind == "title":
            cell = ws.cell(row=r, column=c0, value=block["value"])
            cell.font = _font(st, bold=True, size=st["title_size"], underline="single" if st["profile"] == "form" and srng.random() < 0.3 else None)
            ws.merge_cells(start_row=r, start_column=c0, end_row=r, end_column=c0 + 5)
            cell.alignment = Alignment(horizontal=st["title_align"], vertical="center")
            ws.row_dimensions[r].height = st["title_size"] * 1.8
            if block["approval"]:
                roles = st["roles"]
                head = ws.cell(row=r, column=c0 + 6, value="결재")
                ws.merge_cells(start_row=r, start_column=c0 + 6, end_row=r + 1, end_column=c0 + 6)
                head.alignment, head.font = Alignment(horizontal="center", vertical="center", wrap_text=True), _font(st)
                for rr in (r, r + 1):
                    ws.cell(row=rr, column=c0 + 6).border = st["box"]
                for k, role in enumerate(roles):
                    top = ws.cell(row=r, column=c0 + 7 + k, value=role)
                    top.border, top.font, top.alignment = st["box"], _font(st), Alignment(horizontal="center", vertical="center")
                    ws.cell(row=r + 1, column=c0 + 7 + k, value="").border = st["box"]
                ws.row_dimensions[r + 1].height = 36
            if st["profile"] == "form" and srng.random() < 0.5:
                dept = next((str(v) for b in blocks if b["kind"] == "kv" for k, v in b["pairs"] if k == "부서"), "생산")
                prefix = "생관" if dept.startswith("생산관리") else dept[:2]
                ws.cell(row=r + 2, column=c0, value=f"문서번호: {prefix}-26{srng.randint(10, 12)}-{srng.randint(1, 60):03d}").font = _font(st)
            elif st["profile"] == "erp" and srng.random() < 0.6:
                ws.cell(row=r + 1, column=c0, value="회사명 : ㈜충파모제지").font = _font(st)
            r += 3
        elif kind == "text":
            ws.cell(row=r, column=c0, value=block["value"]).font = _font(st, bold=not str(block["value"]).startswith(("※", "출력일시")))
            r += 1 + rng.choice([0, 1])
        elif kind == "kv":
            drawn = rng.random() < 0.4
            joined_file = drawn if joined_file is None else joined_file
            joined = joined_file
            col = c0
            for i, (k, v) in enumerate(block["pairs"]):
                if i % block["per_row"] == 0:
                    col = c0
                row = r + i // block["per_row"]
                if joined:
                    ws.cell(row=row, column=col, value=f"{k}: {v}").font = _font(st)
                    col = skip(col, _width(f"{k}: {v}") + 2)
                else:
                    value_col = skip(col, _width(k) + 1)
                    label, value = ws.cell(row=row, column=col, value=k), ws.cell(row=row, column=value_col, value=_value(v, st, srng))
                    col = skip(value_col, _width(v) + 2)
                    label.font, value.font = _font(st, bold=st["profile"] != "sap"), _font(st)
                    if isinstance(v, dt.date):
                        value.number_format = st["date_fmt"]
                    if st["profile"] == "form":
                        label.fill, label.alignment = PatternFill("solid", fgColor=st["head_fill"]), Alignment(horizontal="center")
                        for first, last in ((label.column, value_col - 1), (value_col, col - 1)):
                            for cc in range(first, last + 1):
                                ws.cell(row=row, column=cc).border = st["box"]
                            if last > first:
                                ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
            r += (len(block["pairs"]) - 1) // block["per_row"] + 1 + rng.choice([0, 1])
        elif kind == "table":
            headers, rows = block["headers"], block["rows"]
            if block["groups"]:
                col = c0
                for name, span in block["groups"]:
                    if name:
                        cell = ws.cell(row=r, column=col, value=name)
                        cell.font, cell.alignment = _font(st, bold=True, color=st["head_font"]), Alignment(horizontal="center", vertical="center")
                        if span > 1:
                            ws.merge_cells(start_row=r, start_column=col, end_row=r, end_column=col + span - 1)
                        for cc in range(col, col + span):
                            if st["head_fill"]:
                                ws.cell(row=r, column=cc).fill = PatternFill("solid", fgColor=st["head_fill"])
                            ws.cell(row=r, column=cc).border = st["box"]
                    col += span
                r += 1
            header_row = r
            for j, h in enumerate(headers):
                cell = ws.cell(row=r, column=c0 + j, value=SPACED.get(h, h) if st["spaced"] else h)
                cell.font, cell.border = _font(st, bold=True, color=st["head_font"]), st["box"]
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                if st["head_fill"]:
                    cell.fill = PatternFill("solid", fgColor=st["head_fill"])
            ws.row_dimensions[r].height = max(st["size"] * 2.0, 18)
            centered = set()
            for j, h in enumerate(headers):
                strs = [x[j] for x in rows if j < len(x) and isinstance(x[j], str)]
                if str(h).lower() in ("no", "no.", "순번", "번호") or (strs and max(len(x) for x in strs) <= 4):
                    centered.add(j)
            for n, row in enumerate(rows):
                r += 1
                for j, v in enumerate(row):
                    cell = ws.cell(row=r, column=c0 + j, value=_value(v, st, srng, n if len(rows) > 8 else None))
                    cell.font = _font(st)
                    if st["borders"]:
                        cell.border = st["box"]
                    if st["band"] and n % 2:
                        cell.fill = PatternFill("solid", fgColor=st["band"])
                    if isinstance(v, bool):
                        continue
                    if j in centered:
                        cell.alignment = Alignment(horizontal="center")
                    if isinstance(v, int):
                        cell.number_format = ("#,##0;[Red]-#,##0" if st["neg_red"] else "#,##0") if abs(v) >= 1000 or st["neg_red"] else "General"
                    elif isinstance(v, float):
                        cell.number_format = "#,##0.00;[Red]-#,##0.00" if st["neg_red"] else "#,##0.00"
                    elif isinstance(v, dt.date):
                        cell.number_format, cell.alignment = st["date_fmt"], Alignment(horizontal="center")
                    elif isinstance(v, str) and v.endswith("%"):
                        cell.alignment = Alignment(horizontal="right")
                        if v.endswith("%") and v[:-1].strip().replace(".", "", 1).isdigit() and float(v[:-1]) > 100:
                            cell.font = _font(st, bold=True, color="C00000")          # 부하율 100% 초과를 담당자가 빨갛게 표시한 흔적
            total_row = None
            if block["total"] and rows:
                r += 1
                total_row = r
                word = rng.choice(["합계", "계", "Total"])
                korean = any(ord(ch) > 0x1100 for h in headers for ch in str(h))
                ws.cell(row=r, column=c0, value=("합계" if word == "Total" else word) if korean else "Total")
                for j in range(1, len(headers)):
                    nums = [x[j] for x in rows if isinstance(x[j], (int, float)) and not isinstance(x[j], bool)]
                    if len(nums) == len(rows) and not str(headers[j]).lower().startswith(("no", "순번")):
                        letter = get_column_letter(c0 + j)
                        cell = ws.cell(row=r, column=c0 + j, value=f"=SUM({letter}{header_row + 1}:{letter}{r - 1})" if st["formula"] else round(sum(nums), 2))
                        cell.number_format = "#,##0.00" if any(isinstance(x, float) for x in nums) else "#,##0"
                for j in range(len(headers)):
                    cell = ws.cell(row=r, column=c0 + j)
                    cell.font = _font(st, bold=True)
                    cell.border = Border(left=st["line"], right=st["line"], bottom=st["line"], top=Side(style="double" if st["profile"] in ("form", "erp") else "thin"))
                    if st["profile"] in ("form", "erp") and st["head_fill"]:
                        cell.fill = PatternFill("solid", fgColor=st["head_fill"])
                ws.cell(row=r, column=c0).alignment = Alignment(horizontal="center")
            for rr in range(header_row, r + 1):
                for j in range(len(headers)):
                    table_cells.add((rr, c0 + j))
            tables.append({"header": header_row, "first": header_row + 1, "last": header_row + len(rows), "c0": c0, "ncols": len(headers), "total": total_row})
            r += 2
    return tables, r, table_cells


def decorate(ws, srng, tables, last_row, st, author):
    """사람이 쓰던 파일에 남는 흔적: 형광펜, 메모, 취소선, 숨긴 열, 옆에 적어 둔 말, 계산하다 남긴 숫자, 틀 고정, 필터, 인쇄 설정."""
    big = max(tables, key=lambda t: t["last"] - t["first"], default=None)
    if big and big["last"] >= big["first"]:
        def pick():
            return ws.cell(row=srng.randint(big["first"], big["last"]), column=big["c0"] + srng.randrange(big["ncols"]))

        if srng.random() < 0.35:
            fill = YELLOW if srng.random() < 0.7 else PatternFill("solid", fgColor=srng.choice(["FFC7CE", "C6EFCE", "FFEB9C"]))
            for _ in range(srng.randint(1, 6)):
                pick().fill = fill
        if srng.random() < 0.2:
            for _ in range(srng.randint(1, 3)):
                pick().comment = Comment(srng.choice(MEMOS), author)
        if srng.random() < 0.08:
            row = srng.randint(big["first"], big["last"])
            for j in range(big["ncols"]):
                cell = ws.cell(row=row, column=big["c0"] + j)
                cell.font = Font(name=st["font"], size=st["size"], strike=True, color="808080")
        if srng.random() < 0.08 and big["ncols"] > 4:
            ws.column_dimensions[get_column_letter(big["c0"] + srng.randrange(2, big["ncols"]))].hidden = True
        if srng.random() < 0.15:
            ws.cell(row=srng.randint(big["first"], big["last"]), column=big["c0"] + big["ncols"] + 1, value=srng.choice(SIDE_NOTES)).font = Font(
                name=st["font"], size=st["size"], color=srng.choice(["FF0000", "0000FF", "000000"]))
        if srng.random() < 0.1:
            col, row = big["c0"] + big["ncols"] + 2, big["first"] + srng.randint(0, 3)
            nums = [srng.randrange(100, 9000, 50) for _ in range(srng.randint(2, 4))]
            for i, n in enumerate(nums):
                ws.cell(row=row + i, column=col, value=n)
            ws.cell(row=row + len(nums), column=col, value=f"=SUM({get_column_letter(col)}{row}:{get_column_letter(col)}{row + len(nums) - 1})")
        if len(tables) == 1 and big["last"] - big["first"] >= 20 and srng.random() < 0.7:
            ws.freeze_panes = ws.cell(row=big["first"], column=big["c0"] + (1 if st["profile"] == "planner" else 0))
        if len(tables) == 1 and st["profile"] in ("erp", "sap") and srng.random() < 0.5:
            ws.auto_filter.ref = f"{get_column_letter(big['c0'])}{big['header']}:{get_column_letter(big['c0'] + big['ncols'] - 1)}{big['last']}"
        if st["profile"] == "form" and srng.random() < 0.4:
            ws.cell(row=last_row + 1, column=big["c0"], value="㈜충파모제지").font = Font(name=st["font"], size=st["size"] + 1, bold=True)
    ws.sheet_view.showGridLines = st["grid"]
    ws.sheet_view.zoomScale = srng.choice([100, 100, 100, 90, 85, 115])
    ws.page_setup.orientation = srng.choice(["landscape", "portrait"]) if st["profile"] == "form" else "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    if srng.random() < 0.4:
        ws.oddFooter.center.text = "&P / &N"
    if srng.random() < 0.12:
        ws.sheet_properties.tabColor = srng.choice(["FF0000", "FFC000", "00B050", "0070C0"])


def _width(value) -> float:
    if isinstance(value, (dt.date, dt.datetime)):
        return 11
    s = str(value)
    if s.startswith("="):
        return 9
    return sum(2 if ord(ch) > 0x1100 else 1.1 for ch in s)


def write_workbook(path, rng, srng, blocks, offset, extra_sheet, sheet_name, source):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    st = make_style(srng, profile_of(blocks, source))
    author = srng.choice(PEOPLE)
    tables, last_row, table_cells = write_blocks(ws, rng, srng, blocks, offset, st)
    for column in ws.columns:                       # 열 폭은 표 안의 칸 기준. 표가 지나지 않는 열만 그 열의 글 길이를 본다
        inside = [_width(c.value) for c in column if c.value is not None and (c.row, c.column) in table_cells]
        outside = [_width(c.value) for c in column if c.value is not None and not isinstance(c, MergedCell)]
        width = max(inside) if inside else min(max(outside, default=0), 14)
        ws.column_dimensions[get_column_letter(column[0].column)].width = min(max(width + 2.5, 6), 42)
    decorate(ws, srng, tables, last_row, st, author)
    if extra_sheet == "cover":
        cover = wb.create_sheet("표지", 0)
        cover["B2"] = "㈜충파모제지"
        cover["B2"].font = Font(name=st["font"], size=20, bold=True)
        cover["B4"] = rng.choice(["대외비", "내부 검토용", "배포 금지"])
        cover["B4"].font = Font(name=st["font"], size=12, color="FF0000")
        wb.active = 1                               # 표지가 있어도 열면 자료 시트가 먼저 보인다
    elif extra_sheet == "empty":
        wb.create_sheet("Sheet2")
        wb.create_sheet("Sheet3")
    elif extra_sheet == "notes":
        notes = wb.create_sheet("비고")
        notes["A1"] = "작성 안내"
        notes["A2"] = "수치는 검토용 초안입니다."
    else:                                           # v3: 예전 엑셀 기본값인 빈 시트, 지난 버전 사본, 숨긴 시트
        kind = srng.choices(["none", "empty", "copy", "hidden"], [0.6, 0.25, 0.1, 0.05])[0]
        if kind == "empty":
            wb.create_sheet("Sheet2")
            wb.create_sheet("Sheet3")
        elif kind == "copy":
            wb.copy_worksheet(ws).title = srng.choice([f"{sheet_name} (2)", "이전", "수정전", "backup"])
        elif kind == "hidden":
            hidden = wb.create_sheet(srng.choice(["_tmp", "code", "참조"]))
            hidden.sheet_state = "hidden"
            for i, value in enumerate(["Y", "N", "EA", "kg", "BOX"], 1):
                hidden.cell(row=i, column=1, value=value)
    created = dt.datetime(2026, srng.randint(10, 12), srng.randint(1, 28), srng.randint(8, 18), srng.randint(0, 59))
    wb.properties.creator, wb.properties.lastModifiedBy = author, srng.choice(PEOPLE)
    wb.properties.created, wb.properties.modified = created, created + dt.timedelta(days=srng.randint(0, 20), hours=srng.randint(0, 8))
    wb.save(path)


def build() -> list[dict]:
    rng = random.Random(SEED)
    plan = [(cat, i) for cat in TEMPLATES for i in range(PER_CATEGORY)]
    rng.shuffle(plan)
    used, labels = set(), []
    for n, (cat, i) in enumerate(plan, 1):
        template = TEMPLATES[cat][i % len(TEMPLATES[cat])]
        blocks, source, verified = template(rng)
        name_kind = rng.choices(["hint", "neutral"], [0.3, 0.7])[0]
        stem = (rng.choice(FILE_HINTS[cat]) + rng.choice(["_2027-01", "(1월)", "_v2", " 최종", ""])) if name_kind == "hint" else rng.choice(NEUTRAL_FILES)
        filename = f"{stem}.xlsx"
        while filename.lower() in used:                 # 윈도우는 파일명 대소문자를 구분하지 않는다
            filename = f"{stem} ({rng.randint(2, 99)}).xlsx"
        used.add(filename.lower())
        labels.append({"file": filename, "category": cat, "template": template.__name__, "source": source, "verified": verified, "name_kind": name_kind,
                       "split": "dev" if int(hashlib.sha256(f"{n}-{cat}".encode()).hexdigest()[:8], 16) % 10 < 4 else "test",
                       "_write": (blocks, rng.choice([0, 0, 0, 1, 2]), rng.choices(["none", "cover", "empty", "notes"], [0.85, 0.05, 0.04, 0.06])[0],
                                  rng.choice(["Sheet1", "Data", "조회결과", "1월", "raw", "Report"]))})
    return labels


def main() -> None:
    labels = build()
    if INBOX.exists():
        shutil.rmtree(INBOX)
    INBOX.mkdir(parents=True)
    rng = random.Random(SEED + 1)
    for item in labels:
        blocks, offset, extra_sheet, sheet_name = item.pop("_write")
        srng = random.Random(f"{SEED}-style-{item['file']}")       # 파일마다 따로 정하는 꾸밈(글꼴, 색, 메모 등)
        write_workbook(INBOX / item["file"], rng, srng, blocks, offset, extra_sheet, sheet_name, item["source"])
    (HERE / "labels.json").write_text(json.dumps({"seed": SEED, "note": "SYNTHETIC. 실제 기업 자료가 아니다.", "files": labels}, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8")
    counts: dict[str, int] = {}
    for item in labels:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    print(len(labels), counts, "->", INBOX)


if __name__ == "__main__":
    main()
