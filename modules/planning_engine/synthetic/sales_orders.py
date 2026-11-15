"""월 판매량을 주문 건별 ERP 판매(출고) 내역 보고서로 쪼갠다 (SYNTHETIC).

위에서 아래로 쪼갠다: 제품·월 판매량 → 채널 → 주문 슬롯(날짜·거래처) → 주문 행.
거래처명·채널·제품명·단가는 마스터(masters.py)에서 찾아 붙인다. ERP의 '판매 현황' 엑셀 보고서와 같은 모양이다.
'정상' 행의 수량을 주문일 기준으로 월별로 합치면 입력한 월 판매량과 정확히 같다.
취소 행과 반품 행은 그 위에 따로 얹으므로 이 합계에 영향을 주지 않는다.
"""
from __future__ import annotations

import calendar
import math
import random
from datetime import date, timedelta

# 공휴일(근사): 고정 공휴일 + 설·추석 연휴 + 일부 대체공휴일. 실제 달력의 모든 휴일을 담지는 않는다.
FIXED_HOLIDAYS = ["01-01", "03-01", "05-05", "06-06", "08-15", "10-03", "10-09", "12-25"]
LUNAR_HOLIDAYS = [
    "2022-01-31", "2022-02-01", "2022-02-02", "2022-09-09", "2022-09-10", "2022-09-11", "2022-09-12",
    "2023-01-21", "2023-01-22", "2023-01-23", "2023-01-24", "2023-09-28", "2023-09-29", "2023-09-30",
    "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12", "2024-09-16", "2024-09-17", "2024-09-18",
    "2025-01-28", "2025-01-29", "2025-01-30", "2025-10-05", "2025-10-06", "2025-10-07", "2025-10-08",
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-09-24", "2026-09-25", "2026-09-26",
]

INCLUDE_PROB = {"대형마트": 0.9, "편의점·슈퍼": 0.7, "온라인": 0.8, "대리점·도매": 0.8, "기업·업소": 0.9}
SHIP_LAG = {"대형마트": (1, 1), "편의점·슈퍼": (1, 1), "온라인": (0, 1), "대리점·도매": (1, 2), "기업·업소": (2, 3)}
CANCEL_PROB = 0.01
RETURN_PROB = {"대형마트": 0.04, "편의점·슈퍼": 0.03, "대리점·도매": 0.03}   # 행 단위 확률. 전체 반품 수량 약 0.5%

HEADER = ["주문일자", "출고일자", "주문번호", "행번호", "거래처코드", "거래처명", "채널", "제품코드", "제품명",
          "수량", "단위", "단가", "금액", "구분", "원주문번호"]


class Customer:
    def __init__(self, row):
        self.code, self.name, self.channel, self.region, self.order_days, self.weight, start, end = row
        self.start = date.fromisoformat(start)
        self.end = date.fromisoformat(end) if end else date.max

    def active(self, d: date) -> bool:
        return self.start <= d <= self.end


def holidays(years):
    out = {date.fromisoformat(d) for d in LUNAR_HOLIDAYS}
    for y in years:
        out |= {date.fromisoformat(f"{y}-{md}") for md in FIXED_HOLIDAYS}
    return out


class Calendar:
    def __init__(self, years):
        self.off = holidays(years)

    def is_business(self, d):
        return d.weekday() < 5 and d not in self.off

    def add_business_days(self, d, n):
        while not self.is_business(d):          # 휴일 주문은 다음 영업일부터 센다
            d += timedelta(days=1)
        while n > 0:
            d += timedelta(days=1)
            if self.is_business(d):
                n -= 1
        return d


def split_int(total, weights):
    """정수 total을 weights 비율로 나눈다(최대 나머지 방식). 합계는 정확히 total."""
    s = sum(weights)
    raw = [total * w / s for w in weights]
    base = [math.floor(x) for x in raw]
    rest = total - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - base[i], -i), reverse=True)
    for i in order[:rest]:
        base[i] += 1
    return base


def month_slots(y, m, customers, cal, rng):
    """그 달의 (주문일, 거래처) 후보. 거래 기간 밖의 날짜는 넣지 않는다."""
    days = [date(y, m, k) for k in range(1, calendar.monthrange(y, m)[1] + 1)]
    slots = []
    for c in customers:
        mine = [d for d in days if c.active(d)]
        if c.channel == "온라인":
            slots += [(d, c) for d in mine]
        elif c.order_days is None:               # 기업·업소: 월 0~3회 불규칙
            biz = [d for d in mine if cal.is_business(d)]
            for d in rng.sample(biz, k=min(len(biz), rng.choice([0, 1, 1, 2, 2, 3]))):
                slots.append((d, c))
        else:
            slots += [(d, c) for d in mine if d.weekday() in c.order_days and cal.is_business(d)]
    return slots


def build(demand, product_names, years, seed, customer_defs, price_book, channel_shares):
    """demand: {제품: [(YYYY-MM, 수량)]} → 판매 내역 행 목록 (헤더 HEADER 순서)"""
    rng = random.Random(seed)
    cal = Calendar(range(years[0], years[-1] + 2))
    customers = [Customer(r) for r in customer_defs]
    by_code = {c.code: c for c in customers}
    lines = []   # (주문일, 거래처, 제품, 수량)
    for product, series in demand.items():
        shares = channel_shares(product)
        channels = list(shares)
        for period, qty in series:
            if qty == 0:
                continue
            y, m = map(int, period.split("-"))
            for channel, cq in zip(channels, split_int(qty, [shares[c] for c in channels])):
                if cq == 0:
                    continue
                pool = [c for c in customers if c.channel == channel]
                slots = month_slots(y, m, pool, cal, rng)
                chosen = [s for s in slots if rng.random() < INCLUDE_PROB[channel]]
                if not chosen:
                    if slots:
                        chosen = slots[:1]
                    else:                        # 기업·업소가 그달 주문이 없게 뽑힌 경우: 영업일 하루를 골라 준다
                        biz = [date(y, m, k) for k in range(1, calendar.monthrange(y, m)[1] + 1)]
                        cands = [(d, c) for d in biz if cal.is_business(d) for c in pool if c.active(d)]
                        chosen = [rng.choice(cands)]
                weights = []
                for d, c in chosen:
                    w = c.weight * rng.gammavariate(4, 0.25)
                    if channel == "온라인" and d.weekday() >= 5:
                        w *= 1.25
                    weights.append(w)
                for (d, c), q in zip(chosen, split_int(cq, weights)):
                    if q > 0:
                        lines.append((d, c, product, q))

    lines.sort(key=lambda r: (r[0], r[1].code, r[2]))
    rows, order_no, ship_date, seq_by_day, line_no = [], {}, {}, {}, {}
    normal_rows = []
    for d, c, product, q in lines:
        key = (d, c.code)
        if key not in order_no:                   # 같은 날 같은 거래처 주문은 한 주문번호, 한 번에 출고
            seq_by_day[d] = seq_by_day.get(d, 0) + 1
            order_no[key] = f"SO-{d:%y%m%d}-{seq_by_day[d]:03d}"
            lo, hi = SHIP_LAG[c.channel]
            ship_date[key] = cal.add_business_days(d, rng.randint(lo, hi))
        line_no[key] = line_no.get(key, 0) + 1
        price = price_book.price(product, c.channel, d)
        rows.append([d.isoformat(), ship_date[key].isoformat(), order_no[key], line_no[key], c.code, c.name,
                     c.channel, product, product_names[product], q, "팩", price, q * price, "정상", ""])
        normal_rows.append((d, c, product, q, order_no[key], price))
        if rng.random() < CANCEL_PROB:           # 입력 후 취소된 행: 같은 주문에 별도 행으로 남는다
            line_no[key] += 1
            cq = max(1, int(round(q * rng.uniform(0.3, 1.0))))
            rows.append([d.isoformat(), "", order_no[key], line_no[key], c.code, c.name, c.channel, product,
                         product_names[product], cq, "팩", price, cq * price, "취소", ""])

    last_day = date(years[-1], 12, 31)
    returns, ret_seq = [], {}
    for d, c, product, q, so, price in normal_rows:
        p = RETURN_PROB.get(c.channel, 0)
        if p and rng.random() < p:
            rd = d + timedelta(days=rng.randint(7, 21))
            if rd > last_day or not c.active(rd):
                continue
            ret_seq[rd] = ret_seq.get(rd, 0) + 1
            rq = max(1, math.ceil(q * rng.uniform(0.05, 0.3)))
            returns.append([rd.isoformat(), "", f"RT-{rd:%y%m%d}-{ret_seq[rd]:03d}", 1, c.code, c.name, c.channel,
                            product, product_names[product], -rq, "팩", price, -rq * price, "반품", so])
    rows += returns
    rows.sort(key=lambda r: (r[0], r[2], r[3]))
    assert all(by_code[r[4]].active(date.fromisoformat(r[0])) for r in rows)
    return rows
