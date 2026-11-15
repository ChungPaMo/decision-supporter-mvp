"""raw 거래 기록만 읽어 재고가 맞물리는지 확인하고, 월별 설비 사용시간을 집계한다 (SYNTHETIC).

확인하는 것
  1. 날짜별 재고: 1월 기초(재고수불부) + 생산입고 + 구매입고 + 반품입고 − 판매출고 − 생산투입 − 반품폐기
     가 어느 날도 0 밑으로 내려가지 않고, 12/31 값이 재고현황_20261231과 같다.
  2. 재고수불부의 월별 숫자가 거래 기록 합계와 같다.
  3. 자재투입 = 지시수량 × BOM 소요량 × (1 + 손실률) (반올림), 생산·투입 날짜가 같다.
  4. 발주별 입고 합계 = 발주의 입고수량, 미입고 발주 = 미입고발주현황, 단가 = 구매단가표(발주일 기준).
  5. 생산·입고는 평일에만 있다.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path


def read(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def r_int(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def check(raw: Path, year: int = 2026):
    t, m, s = raw / "transactions", raw / "master", raw / "snapshots"
    production = read(t / f"생산실적_{year}.csv")
    issues = read(t / f"자재투입내역_{year}.csv")
    receipts = read(t / f"입고내역_{year}.csv")
    pos = read(t / f"구매발주내역_{year}.csv")
    ledger = read(t / f"재고수불부_{year}.csv")
    stock = {r["품목코드"]: int(r["현재고"]) for r in read(s / f"재고현황_{year}1231.csv")}
    open_po = read(s / f"미입고발주현황_{year}1231.csv")
    problems = []

    # ---- 일별 흐름 ----
    moves = {}                                       # (품목, 날짜) → 증감

    def add(item, d, q):
        moves[(item, d)] = moves.get((item, d), 0) + q

    flows = {}                                       # (품목, 월, 항목) → 수량

    def flow(item, d, col, q):
        flows[(item, d[:7], col)] = flows.get((item, d[:7], col), 0) + q

    for f in sorted(t.glob("판매현황_*.csv")):
        for r in read(f):
            if r["구분"] == "정상" and r["출고일자"].startswith(str(year)):
                add(r["제품코드"], r["출고일자"], -int(r["수량"]))
                flow(r["제품코드"], r["출고일자"], "판매출고", int(r["수량"]))
            elif r["구분"] == "반품" and r["주문일자"].startswith(str(year)):
                flow(r["제품코드"], r["주문일자"], "반품입고", -int(r["수량"]))
                flow(r["제품코드"], r["주문일자"], "반품폐기", -int(r["수량"]))   # 검수 후 전량 폐기: 순증감 0
    for r in production:
        add(r["제품코드"], r["생산일자"], int(r["양품수량"]))
        flow(r["제품코드"], r["생산일자"], "생산입고", int(r["양품수량"]))
        if int(r["지시수량"]) != int(r["양품수량"]) + int(r["불량수량"]):
            problems.append(f"지시 ≠ 양품 + 불량 {r['작업지시번호']}")
    for r in issues:
        add(r["자재코드"], r["투입일자"], -int(r["투입수량"]))
        flow(r["자재코드"], r["투입일자"], "생산투입", int(r["투입수량"]))
    for r in receipts:
        add(r["자재코드"], r["입고일"], int(r["입고수량"]))
        flow(r["자재코드"], r["입고일"], "구매입고", int(r["입고수량"]))

    # ---- 1·2. 수불부와 일별 재고 ----
    cols = ["생산입고", "구매입고", "반품입고", "판매출고", "생산투입", "반품폐기"]
    opening, prev_end = {}, {}
    for r in ledger:
        code, month = r["품목코드"], r["월"]
        if month.endswith("-01"):
            opening[code] = int(r["기초재고"])
        elif int(r["기초재고"]) != prev_end.get(code):
            problems.append(f"수불부 기초 ≠ 전월 기말 {code} {month}")
        for c in cols:
            if int(r[c]) != flows.get((code, month, c), 0):
                problems.append(f"수불부 {c}가 거래 합계와 다름 {code} {month}")
        calc = int(r["기초재고"]) + sum(int(r[c]) for c in cols[:3]) - sum(int(r[c]) for c in cols[3:])
        if calc != int(r["기말재고"]):
            problems.append(f"수불부 기말 계산 불일치 {code} {month}")
        prev_end[code] = int(r["기말재고"])
    for code, bal in opening.items():
        for d in sorted({d for (i, d) in moves if i == code}):
            bal += moves[(code, d)]
            if bal < 0:
                problems.append(f"재고가 음수 {code} {d} {bal}")
                break
        if bal != stock.get(code):
            problems.append(f"12/31 재고가 재고현황과 다름 {code}: 거래 {bal} / 재고현황 {stock.get(code)}")
    if set(opening) != set(stock):
        problems.append("수불부 품목과 재고현황 품목이 다름")

    # ---- 3. 자재투입 = BOM ----
    bom = {}
    for b in read(m / "BOM.csv"):
        bom.setdefault(b["제품코드"], []).append((b["자재코드"], Decimal(b["소요량"]), Decimal(b["손실률(%)"]) / 100))
    expected = {}
    for r in production:
        for mat, per, loss in bom[r["제품코드"]]:
            expected[(r["작업지시번호"], mat)] = (r["생산일자"], r_int(int(r["지시수량"]) * per * (1 + loss)))
    actual = {(r["작업지시번호"], r["자재코드"]): (r["투입일자"], int(r["투입수량"])) for r in issues}
    if actual != expected:
        bad = sorted(set(actual.items()) ^ set(expected.items()))[:3]
        problems.append(f"자재투입이 BOM 계산과 다름 {bad}")

    # ---- 4. 발주·입고·단가 ----
    prices = read(m / "구매단가표.csv")

    def price_on(mat, d):
        return next(int(p["단가"]) for p in prices
                    if p["자재코드"] == mat and p["적용시작일"] <= d and (not p["적용종료일"] or d <= p["적용종료일"]))

    got = {}
    po_by_no = {p["발주번호"]: p for p in pos}
    for r in receipts:
        got[r["발주번호"]] = got.get(r["발주번호"], 0) + int(r["입고수량"])
        po = po_by_no.get(r["발주번호"])
        if po is None:
            problems.append(f"발주 없는 입고 {r['입고번호']}")
            continue
        if (r["자재코드"], r["단가"]) != (po["자재코드"], po["단가"]) or r["입고일"] < po["발주일"]:
            problems.append(f"입고가 발주와 맞지 않음 {r['입고번호']}")
        if int(r["입고수량"]) * int(r["단가"]) != int(r["금액"]):
            problems.append(f"입고 금액 계산 불일치 {r['입고번호']}")
    for p in pos:
        if got.get(p["발주번호"], 0) != int(p["입고수량"]):
            problems.append(f"발주 입고수량 ≠ 입고 합계 {p['발주번호']}")
        if int(p["발주수량"]) - int(p["입고수량"]) != int(p["미입고수량"]):
            problems.append(f"미입고수량 계산 불일치 {p['발주번호']}")
        if int(p["단가"]) != price_on(p["자재코드"], p["발주일"]):
            problems.append(f"발주 단가가 구매단가표와 다름 {p['발주번호']}")
        if int(p["발주수량"]) * int(p["단가"]) != int(p["금액"]):
            problems.append(f"발주 금액 계산 불일치 {p['발주번호']}")
    still_open = {(p["발주번호"], p["자재코드"], p["미입고수량"], p["납기예정일"]) for p in pos if int(p["미입고수량"])}
    snapshot = {(p["발주번호"], p["자재코드"], p["미입고수량"], p["납기예정일"]) for p in open_po}
    if still_open != snapshot:
        problems.append(f"미입고 발주가 미입고발주현황과 다름 {sorted(still_open ^ snapshot)}")

    # ---- 5. 평일 ----
    for r in production:
        if date.fromisoformat(r["생산일자"]).weekday() >= 5:
            problems.append(f"주말 생산 {r['작업지시번호']}")
    for r in receipts:
        if date.fromisoformat(r["입고일"]).weekday() >= 5:
            problems.append(f"주말 입고 {r['입고번호']}")
    return problems


def capacity_usage(raw: Path, year: int = 2026):
    """생산실적의 설비·작업 시간을 (자원, 월)별로 합친다. 반환: [(자원, 월, 시간)]"""
    used = {}
    for r in read(raw / "transactions" / f"생산실적_{year}.csv"):
        month = r["생산일자"][:7]
        for res_col, h_col in (("되감기설비", "되감기시간(h)"), ("절단설비", "절단시간(h)"), ("포장설비", "포장시간(h)")):
            key = (r[res_col], month)
            used[key] = used.get(key, Decimal(0)) + Decimal(r[h_col])
        used[("LB1", month)] = used.get(("LB1", month), Decimal(0)) + Decimal(r["포장작업인시(h)"])
    return used
