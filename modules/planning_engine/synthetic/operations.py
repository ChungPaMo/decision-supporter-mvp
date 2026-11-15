"""2026년 생산·자재투입·구매발주·입고 기록 (SYNTHETIC).

판매현황(출고)과 2026-12-31 재고현황은 이미 정해져 있다. 그래서 12/31에서 거꾸로 하루씩 거슬러 올라가며
"그날 출고된 만큼은 그 전에 있었어야 한다"를 쌓고, 쌓인 양이 충분하면 그날 생산(또는 입고)한 것으로 기록한다.
이렇게 하면 기말재고가 재고현황과 정확히 같고, 어느 날도 재고가 0 밑으로 내려가지 않는다.
설비 하루 가용시간을 넘는 생산은 그 전날들로 밀려나므로, 바쁜 달(명절 전) 앞에는 미리 만들어 두는 모양이 자연히 생긴다.

반품은 검수 후 전량 폐기한다(반품입고와 같은 날 폐기). 판매 가능한 재고는 늘지 않는다.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

START, END = date(2026, 1, 1), date(2026, 12, 31)
CAPACITY_USE = Decimal("0.98")       # 시뮬레이션은 하루 가용시간의 98%까지만 채운다 (실적 시간의 흔들림 여유)
DEFECT_RATE = (0.004, 0.012)         # 생산 불량률
EFFICIENCY = (0.96, 1.04)            # 실제 작업시간 / 표준시간
MIN_LOT_DAYS, MAX_LOT_DAYS = 2.5, 8  # 한 번 생산할 때 하루 출고량의 몇 배를 만드는가
LOW_COVER_DAYS = (1.0, 2.0)          # 생산 직전 남아 있는 재고 (하루 출고량의 배수)

# 자재 구매 방식: (한 번 주문량 = 하루 평균 사용량 × 일수, 수량 단위)
ORDER_DAYS = {"원단": 10, "부자재": 10, "포장재": 12}
ORDER_STEP = {"MR-N3": 500, "MR-N2": 500, "MR-N4": 500, "MR-R2": 500, "MC-CORE": 10000,
              "MP-FILM30": 1000, "MP-FILM24": 1000, "MP-GIFTBOX": 100, "MP-JUMBOBOX": 100}
SPLIT_PROB = 0.12                    # 원단 발주 중 두 번에 나눠 들어오는 비율

PRODUCTION_HEADER = ["생산일자", "작업지시번호", "제품코드", "제품명", "지시수량", "양품수량", "불량수량", "단위",
                     "되감기설비", "되감기시간(h)", "절단설비", "절단시간(h)", "포장설비", "포장시간(h)", "포장작업인시(h)"]
ISSUE_HEADER = ["투입일자", "작업지시번호", "제품코드", "자재코드", "자재명", "투입수량", "단위"]
PO_HEADER = ["발주일", "발주번호", "공급사코드", "공급사명", "자재코드", "자재명", "발주수량", "단위", "단가", "금액",
             "납기예정일", "입고수량", "미입고수량", "진행상태"]
RECEIPT_HEADER = ["입고일", "입고번호", "발주번호", "공급사코드", "공급사명", "자재코드", "자재명", "입고수량", "단위",
                  "단가", "금액", "입고창고"]
LEDGER_HEADER = ["월", "품목구분", "품목코드", "품목명", "단위", "기초재고", "생산입고", "구매입고", "반품입고",
                 "판매출고", "생산투입", "반품폐기", "기말재고"]


def r_int(x) -> int:
    return int(Decimal(str(x)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def hours1(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def ym(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


class Plant:
    """설비 하루 가용시간과 제품별 단위당 작업시간."""

    def __init__(self, routes, labor_per_1000, hours, cal):
        self.routes, self.labor, self.cal = routes, labor_per_1000, cal
        jan = [d for d in days(date(2027, 1, 1), date(2027, 1, 31)) if cal.is_business(d)]
        self.reg_per_day = {r: Decimal(h["2027-01"][0]) / len(jan) for r, h in hours.items()}
        self.ot_per_month = {r: Decimal(h["2027-01"][1]) for r, h in hours.items()}
        self.biz = {}
        for d in days(START, END):
            if cal.is_business(d):
                self.biz[ym(d)] = self.biz.get(ym(d), 0) + 1

    def budget(self, r, month) -> Decimal:
        """한 달 쓸 수 있는 시간 = 영업일 × 하루 정규시간 + 잔업 한도"""
        return self.reg_per_day[r] * self.biz[month] + self.ot_per_month[r]

    def day_capacity(self, d):
        m = ym(d)
        return {r: self.budget(r, m) / self.biz[m] * CAPACITY_USE for r in self.reg_per_day}

    def unit_hours(self, product):
        """1팩 만들 때 자원별 표준시간"""
        out = {}
        for _, res, ref, hrs in self.routes[product]:
            out[res] = out.get(res, Decimal(0)) + Decimal(hrs) / ref
            if res in self.labor:
                out["LB1"] = out.get("LB1", Decimal(0)) + Decimal(self.labor[res]) / 1000
        return out


def shipments_2026(order_rows):
    """정상 행은 출고일 기준 출고, 반품 행은 반품일 기준 반품입고(→ 같은 날 폐기)."""
    ship, ret = {}, {}
    for r in order_rows:
        if r[13] == "정상" and r[1]:
            d = date.fromisoformat(r[1])
            if START <= d <= END:
                ship[(r[7], d)] = ship.get((r[7], d), 0) + r[9]
        elif r[13] == "반품":
            d = date.fromisoformat(r[0])
            if START <= d <= END:
                ret[(r[7], d)] = ret.get((r[7], d), 0) - r[9]
    return ship, ret


def plan_production(products, ship, fg_end, plant, cal, monthly_limit, rng):
    """12/31에서 거꾸로 생산 기록을 만든다. 반환: [(날짜, 제품, 지시수량, 양품, 불량)], 기초재고"""
    month_ship = {}
    for (p, d), q in ship.items():
        month_ship[(p, ym(d))] = month_ship.get((p, ym(d)), 0) + q
    year_rate = {p: sum(q for (pp, _), q in ship.items() if pp == p) / sum(plant.biz.values()) for p in products}

    def rate(p, d):                     # 그 달 하루 평균 출고량 (비수기에도 연평균의 30%는 본다)
        return max(month_ship.get((p, ym(d)), 0) / plant.biz[ym(d)], year_rate[p] * 0.3, 1)

    unit_h = {p: plant.unit_hours(p) for p in products}
    inv = dict(fg_end)
    orders, limit_used = [], {}
    for d in sorted(days(START, END), reverse=True):
        x = {p: inv[p] + ship.get((p, d), 0) for p in products}     # 그날 생산 직후·출고 직전 재고
        if cal.is_business(d):
            left = plant.day_capacity(d)
            for p in sorted(products, key=lambda p: x[p] / rate(p, d), reverse=True):
                r = rate(p, d)
                avail = x[p] - r * rng.uniform(*LOW_COVER_DAYS)
                min_lot = max(r * MIN_LOT_DAYS, 30)
                if avail < min_lot:
                    continue
                defect_rate = rng.uniform(*DEFECT_RATE)
                qty = min(avail, r * MAX_LOT_DAYS) / (1 - defect_rate)
                qty = min([qty] + [left[res] / h for res, h in unit_h[p].items()])
                if p in monthly_limit:
                    qty = min(qty, (monthly_limit[p] - limit_used.get((p, ym(d)), 0)) / (1 - defect_rate))
                qty = int(qty // 10) * 10
                if qty < max(r * 0.5, 30):      # 남은 시간이 짧으면 작은 로트로 이어서 생산
                    continue
                defect = r_int(qty * defect_rate)
                good = qty - defect
                for res, h in unit_h[p].items():
                    left[res] -= h * qty
                if p in monthly_limit:
                    limit_used[(p, ym(d))] = limit_used.get((p, ym(d)), 0) + good
                x[p] -= good
                orders.append((d, p, qty, good, defect))
        inv = x
    orders.sort(key=lambda o: (o[0], products.index(o[1])))
    return orders, inv


def plan_receipts(material, kind, moq, safety, consumption, mat_end, cal, rng):
    """자재 하나의 입고 기록을 12/31에서 거꾸로 만든다. 반환: [(날짜, 수량)], 기초재고"""
    biz_days = [d for d in days(START, END) if cal.is_business(d)]
    avg = sum(consumption.values()) / len(biz_days)
    step = ORDER_STEP[material]
    target = max(moq, math.ceil(avg * ORDER_DAYS[kind] / step) * step)
    spacing = max(2, ORDER_DAYS[kind] // 2)
    # 입고 직전 재고 수준: 기말재고가 평소 수준이 되도록 (기말 − 주문량의 75%), 안전재고보다는 높게
    base_low = max(safety, mat_end - target * 0.75)
    inv, receipts, since = mat_end, [], spacing
    for d in sorted(days(START, END), reverse=True):
        y = inv + consumption.get(d, 0)
        if cal.is_business(d):
            since += 1
            low = max(safety, base_low * rng.uniform(0.9, 1.1))
            if since >= spacing and y - low >= target:
                qty = min(int((y - low) // step) * step, target * 2)
                receipts.append((d, qty))
                y -= qty
                since = 0
        inv = y
    receipts.reverse()
    return receipts, inv


def build(*, products, names, order_rows, fg_end, mat_end, bom, routes, labor_per_1000, hours, monthly_limit,
          materials, suppliers, price_rows, scheduled, cal, seed):
    rng = random.Random(seed)
    plant = Plant(routes, labor_per_1000, hours, cal)
    ship, ret = shipments_2026(order_rows)
    orders, fg_open = plan_production(products, ship, fg_end, plant, cal, monthly_limit, rng)

    # ---- 생산실적 + 자재투입 ----
    mat_info = {m[0]: m for m in materials}      # (코드, 이름, 구분, 단위, …, 공급사 7, MOQ 8, 안전재고 9, …)
    production, issues, consumption, used_hours = [], [], {}, {}
    wo_seq = {}
    for d, p, qty, good, defect in orders:
        wo_seq[d] = wo_seq.get(d, 0) + 1
        wo = f"WO-{d:%y%m%d}-{wo_seq[d]:02d}"
        times = {}
        for _, res, ref, hrs in routes[p]:
            times[res] = hours1(qty * hrs / ref * rng.uniform(*EFFICIENCY))
        pack = routes[p][2][1]
        labor = hours1(qty * labor_per_1000[pack] / 1000 * rng.uniform(*EFFICIENCY))
        rw, saw, pk = (s[1] for s in routes[p])
        production.append([d.isoformat(), wo, p, names[p], qty, good, defect, "팩",
                           rw, times[rw], saw, times[saw], pk, times[pk], labor])
        for res, h in list(times.items()) + [("LB1", labor)]:
            used_hours[(res, ym(d))] = used_hours.get((res, ym(d)), Decimal(0)) + h
        for mat, per, unit, scrap in bom[p]:
            q = r_int(Decimal(qty) * Decimal(per) * (1 + Decimal(scrap)))
            consumption.setdefault(mat, {})
            consumption[mat][d] = consumption[mat].get(d, 0) + q
            issues.append([d.isoformat(), wo, p, mat, mat_info[mat][1], q, "개" if unit == "EA" else unit])

    # ---- 자재별 입고 → 발주 ----
    sup_name = {s[0]: s[1] for s in suppliers}

    def price_row(mat, d):
        for row in price_rows:          # (자재, 공급사, 단가, 통화, 단위, 납품기간, MOQ, 시작, 종료)
            if row[0] == mat and row[7] <= d.isoformat() and (not row[8] or d.isoformat() <= row[8]):
                return row
        raise ValueError(f"구매단가 없음 {mat} {d}")

    mat_open, po_groups = {}, []          # po_groups: (자재, [(입고일, 수량)])
    for code, name, kind, unit, *_ in materials:
        m = mat_info[code]
        receipts, mat_open[code] = plan_receipts(code, kind, m[8], int(m[9]), consumption.get(code, {}),
                                                 mat_end[code], cal, rng)
        biz_index = [d for d in days(START, END) if cal.is_business(d)]
        for d, qty in receipts:
            if kind == "원단" and rng.random() < SPLIT_PROB:
                i = biz_index.index(d) - rng.randint(2, 4)
                step = ORDER_STEP[code]
                first = int(qty * rng.uniform(0.5, 0.7) // step) * step
                if i >= 0 and step <= first < qty:
                    po_groups.append((code, [(biz_index[i], first), (d, qty - first)]))
                    continue
            po_groups.append((code, [(d, qty)]))

    def prev_business(d):
        while not cal.is_business(d):
            d -= timedelta(days=1)
        return d

    pos = []
    for code, parts in po_groups:
        first_day = parts[0][0]
        r = rng.random()
        delay = 0 if r < 0.75 else (rng.randint(1, 3) if r < 0.9 else -rng.randint(1, 2))
        lead = price_row(code, first_day - timedelta(days=30))[5]
        po_day = prev_business(first_day - timedelta(days=delay + lead))
        row = price_row(code, po_day)
        due = cal.add_business_days(po_day + timedelta(days=row[5]), 0)
        pos.append([po_day, code, row[1], sum(q for _, q in parts), row[2], due, parts])
    for po, mat, qty, unit, due, sup in scheduled:
        po_day = date(2026, 12, 28)
        pos.append([po_day, mat, sup, qty, price_row(mat, po_day)[2], date.fromisoformat(due), [], po])
    pos.sort(key=lambda p: (p[0], [m[0] for m in materials].index(p[1])))
    seq = {}
    for p in pos:
        if len(p) == 8:                   # 이미 번호가 있는 미입고 발주
            key = p[7][3:7]
            seq[key] = max(seq.get(key, 0), int(p[7][-3:]))
    for p in pos:
        if len(p) == 7:
            key = f"{p[5]:%y%m}"
            seq[key] = seq.get(key, 0) + 1
            p.append(f"PO-{key}-{seq[key]:03d}")

    po_rows, receipt_rows, gr_seq = [], [], {}
    receipt_list = []
    for po_day, mat, sup, qty, price, due, parts, po_no in pos:
        received = sum(q for _, q in parts)
        unit = mat_info[mat][3]
        po_rows.append([po_day.isoformat(), po_no, sup, sup_name[sup], mat, mat_info[mat][1], qty,
                        "개" if unit == "EA" else unit, price, qty * price, due.isoformat(), received, qty - received,
                        "입고완료" if received == qty else "미입고"])
        for d, q in parts:
            receipt_list.append((d, po_no, sup, mat, q, price))
    receipt_list.sort(key=lambda r: (r[0], r[1]))
    for d, po_no, sup, mat, q, price in receipt_list:
        gr_seq[d] = gr_seq.get(d, 0) + 1
        unit = mat_info[mat][3]
        receipt_rows.append([d.isoformat(), f"GR-{d:%y%m%d}-{gr_seq[d]:03d}", po_no, sup, sup_name[sup], mat,
                             mat_info[mat][1], q, "개" if unit == "EA" else unit, price, q * price,
                             "원자재창고" if mat_info[mat][2] == "원단" else "부자재창고"])

    # ---- 재고수불부 (월별) ----
    flows = {}                            # (품목, 월, 항목) → 수량

    def add(item, d, col, q):
        flows[(item, ym(d), col)] = flows.get((item, ym(d), col), 0) + q

    for (p, d), q in ship.items():
        add(p, d, "판매출고", q)
    for (p, d), q in ret.items():
        add(p, d, "반품입고", q)
        add(p, d, "반품폐기", q)
    for d, p, qty, good, defect in orders:
        add(p, d, "생산입고", good)
    for d, po_no, sup, mat, q, price in receipt_list:
        add(mat, d, "구매입고", q)
    for mat, by_day in consumption.items():
        for d, q in by_day.items():
            add(mat, d, "생산투입", q)
    ledger = []
    items = [("제품", p, names[p], "팩", fg_open[p]) for p in products] + \
            [({"원단": "원자재"}.get(m[2], m[2]), m[0], m[1], "개" if m[3] == "EA" else m[3], mat_open[m[0]])
             for m in materials]
    months = [f"2026-{k:02d}" for k in range(1, 13)]
    ins, outs = ["생산입고", "구매입고", "반품입고"], ["판매출고", "생산투입", "반품폐기"]
    for kind, code, name, unit, opening in items:
        bal = opening
        for m in months:
            vals = {c: flows.get((code, m, c), 0) for c in ins + outs}
            end = bal + sum(vals[c] for c in ins) - sum(vals[c] for c in outs)
            ledger.append([m, kind, code, name, unit, bal, *[vals[c] for c in ins + outs], end])
            bal = end
    return {"production": production, "issues": issues, "po": po_rows, "receipts": receipt_rows,
            "ledger": ledger, "used_hours": used_hours, "plant": plant, "fg_open": fg_open, "mat_open": mat_open}
