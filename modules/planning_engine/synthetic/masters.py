"""㈜충파모제지 기준정보(마스터) 테이블 (SYNTHETIC).

ERP 안에 있다고 가정하는 기준정보다. 판매 내역 보고서와 업로드 파일은 모두 이 마스터에서 조합·추출한다.
    공급사 ──< 구매 단가표 >── 자재 ──< BOM >── 제품 ──< 판매 단가표
    거래처 ──────────────────────────────────── 판매 내역(보고서)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

# ---------------------------------------------------------------------------
# ① 공급사
# ---------------------------------------------------------------------------
SUPPLIER_HEADER = ["공급사코드", "공급사명", "공급품목군", "지역", "거래시작일", "결제조건", "기본납품기간(일)"]
SUPPLIERS = [
    ("SUP-PULP-A", "가상펄프상사", "천연펄프 원단", "수입", "2018-03-01", "월말 마감 익월 60일", 21),
    ("SUP-PULP-B", "가상원지공업", "천연펄프 원단(4겹)", "국내", "2021-06-01", "월말 마감 익월 45일", 30),
    ("SUP-RECYCLE", "가상재생제지", "재생펄프 원단", "국내", "2017-09-01", "월말 마감 익월 45일", 14),
    ("SUP-CORE", "가상지관산업", "지관", "국내", "2016-04-01", "월말 마감 익월 30일", 7),
    ("SUP-PACK", "가상포장", "포장재", "국내", "2016-04-01", "월말 마감 익월 30일", 10),
]

# ---------------------------------------------------------------------------
# ② 자재 + ③ 구매 단가표
# ---------------------------------------------------------------------------
MATERIAL_HEADER = ["자재코드", "자재명", "자재구분", "단위", "겹수", "평량(g/m2)", "원단폭(m)", "주공급사코드",
                   "구매단위", "최소주문량", "안전재고", "사용여부"]
# (코드, 이름, 구분, 단위, 겹수, 평량, 폭, 주공급사, 최소주문량, 안전재고, 현재 단가(원/단위), 납품기간(일))
MATERIALS = [
    ("MR-N3", "천연펄프 3겹 원단 점보롤", "원단", "kg", 3, 15, "2.7", "SUP-PULP-A", 5000, "3000", 1800, 21),
    ("MR-N2", "천연펄프 2겹 원단 점보롤", "원단", "kg", 2, 15, "2.7", "SUP-PULP-A", 5000, "2000", 1700, 21),
    ("MR-N4", "천연펄프 4겹 원단 점보롤", "원단", "kg", 4, 14, "2.7", "SUP-PULP-B", 2000, "500", 2200, 30),
    ("MR-R2", "재생펄프 2겹 원단 점보롤", "원단", "kg", 2, 15, "2.7", "SUP-RECYCLE", 3000, "1500", 1100, 14),
    ("MC-CORE", "지관(심지)", "부자재", "EA", None, None, None, "SUP-CORE", 100000, "50000", 25, 7),
    ("MP-FILM30", "포장필름 30롤용", "포장재", "EA", None, None, None, "SUP-PACK", 10000, "3000", 120, 10),
    ("MP-FILM24", "포장필름 24롤용", "포장재", "EA", None, None, None, "SUP-PACK", 5000, "1000", 100, 10),
    ("MP-GIFTBOX", "선물세트 박스", "포장재", "EA", None, None, None, "SUP-PACK", 1000, "300", 900, 14),
    ("MP-JUMBOBOX", "업소용 외박스", "포장재", "EA", None, None, None, "SUP-PACK", 1000, "200", 600, 10),
]
PURCHASE_PRICE_HEADER = ["자재코드", "공급사코드", "단가", "통화", "단위", "납품기간(일)", "최소주문량", "적용시작일", "적용종료일"]
# 현재 단가 대비 기간별 비율. 원단은 2023~2024년 펄프 가격 급등 후 일부 하락, 부자재·포장재는 2024년 한 번 인상(가정).
PAPER_PRICE_INDEX = [("2022-01-01", "0.85"), ("2023-01-01", "0.95"), ("2024-01-01", "1.08"),
                     ("2025-01-01", "1.03"), ("2026-01-01", "1.00")]
OTHER_PRICE_INDEX = [("2022-01-01", "0.95"), ("2024-01-01", "1.00")]

# ---------------------------------------------------------------------------
# ④ 제품
# ---------------------------------------------------------------------------
PRODUCT_HEADER = ["제품코드", "제품명", "브랜드", "제품유형", "원단종류", "겹수", "롤길이(m)", "롤수", "기준단위",
                  "박스입수(팩)", "현재정가(원)", "출시일", "단종일", "판매상태", "안전재고"]
# (브랜드, 원단 자재, 겹수, 롤 길이 m, 롤 수, 박스입수, 2022년 정가, 출시일)
PRODUCT_SPEC = {
    "CP-N3-3030": ("충파모 순수", "MR-N3", 3, 30, 30, 4, 15900, "2016-03-01"),
    "CP-N3-2730": ("충파모 순수", "MR-N3", 3, 27, 30, 4, 14500, "2017-05-01"),
    "CP-N3-2524": ("충파모 순수", "MR-N3", 3, 25, 24, 6, 10900, "2018-09-01"),
    "CP-N2-3030": ("충파모 데일리", "MR-N2", 2, 30, 30, 4, 10500, "2016-03-01"),
    "CP-R2-3030": ("충파모 에코", "MR-R2", 2, 30, 30, 4, 7900, "2019-02-01"),
    "CP-P4-2524": ("충파모 프리미엄", "MR-N4", 4, 25, 24, 6, 16900, "2021-09-01"),
    "CP-GIFT-12": ("충파모 선물세트", "MR-N3", 3, 30, 12, 8, 8900, "2018-01-01"),
    "CP-ON3-3030": ("충파모 순수 온라인", "MR-N3", 3, 30, 30, 4, 15500, "2025-07-01"),
    "CP-B2-JUMBO": ("충파모 프로", "MR-N2", 2, 300, 16, 1, 49000, "2019-06-01"),
}
ROLL_WIDTH_M = Decimal("0.1")

# ---------------------------------------------------------------------------
# ⑤ 판매 단가표
# ---------------------------------------------------------------------------
SALES_PRICE_HEADER = ["제품코드", "채널", "공급가", "적용시작일", "적용종료일"]
CHANNEL_PRICE_RATE = {"대형마트": "0.80", "편의점·슈퍼": "0.90", "온라인": "0.85", "대리점·도매": "0.75", "기업·업소": "0.88"}
PRICE_RAISE_RATE = Decimal("1.03")          # 매년 3월 1일 인상
GENERAL_CHANNELS = {"대형마트": 0.45, "편의점·슈퍼": 0.15, "온라인": 0.20, "대리점·도매": 0.15, "기업·업소": 0.05}
CHANNEL_SHARE = {
    "CP-ON3-3030": {"온라인": 1.0},
    "CP-B2-JUMBO": {"기업·업소": 0.6, "대리점·도매": 0.4},
    "CP-GIFT-12": {"대형마트": 0.5, "온라인": 0.3, "기업·업소": 0.2},
}

# ---------------------------------------------------------------------------
# ⑥ 거래처
# ---------------------------------------------------------------------------
CUSTOMER_HEADER = ["거래처코드", "거래처명", "채널", "지역", "발주요일", "거래시작일", "거래종료일", "결제조건",
                   "거래상태", "담당영업코드"]
PAYMENT_TERMS = {"대형마트": "월말 마감 익월 60일", "편의점·슈퍼": "월말 마감 익월 45일", "온라인": "월말 마감 익월 15일",
                 "대리점·도매": "월말 마감 익월 30일", "기업·업소": "월말 마감 익월 30일"}
SALES_REP = {"대형마트": "S01", "편의점·슈퍼": "S02", "온라인": "S03", "대리점·도매": "S04", "기업·업소": "S05"}
# (코드, 이름, 채널, 지역, 발주 요일(월=0) 또는 None, 규모 계수, 거래 시작일, 거래 종료일)
# 규모 계수는 생성용 내부 값이며 마스터 파일에는 쓰지 않는다.
CUSTOMERS = [
    ("C-MART-A1", "대형마트A 평택물류센터", "대형마트", "경기", (0, 3), 1.3, "2014-04-01", None),
    ("C-MART-A2", "대형마트A 이천물류센터", "대형마트", "경기", (0, 3), 1.0, "2016-09-01", None),
    ("C-MART-B1", "대형마트B 용인물류센터", "대형마트", "경기", (1, 4), 1.2, "2015-02-01", None),
    ("C-MART-B2", "대형마트B 대전물류센터", "대형마트", "충청", (1, 4), 0.8, "2017-06-01", None),
    ("C-MART-C1", "대형마트C 오산물류센터", "대형마트", "경기", (0, 2), 1.0, "2016-01-01", None),
    ("C-MART-C2", "대형마트C 칠곡물류센터", "대형마트", "영남", (0, 2), 0.7, "2019-03-01", None),
    ("C-CVS-G", "편의점G 중부물류", "편의점·슈퍼", "충청", (0, 2, 4), 1.2, "2017-01-01", None),
    ("C-CVS-S", "편의점S 수도권물류", "편의점·슈퍼", "경기", (0, 2, 4), 1.0, "2018-05-01", None),
    ("C-SPM-L", "슈퍼마켓L 통합물류", "편의점·슈퍼", "경기", (0, 2, 4), 0.8, "2015-07-01", None),
    ("C-ONL-C", "오픈마켓C 풀필먼트", "온라인", "경기", None, 1.5, "2019-08-01", None),
    ("C-ONL-N", "오픈마켓N 스토어", "온라인", "서울", None, 1.0, "2020-03-01", None),
    ("C-ONL-G", "오픈마켓G 물류", "온라인", "경기", None, 0.7, "2023-04-01", None),          # 2023년 신규 입점
    ("C-ONL-OWN", "충파모제지 자사몰", "온라인", "충청", None, 0.5, "2021-01-01", None),
    ("C-AGT-SE", "서울동부 대리점", "대리점·도매", "서울", (1,), 1.0, "2012-05-01", None),
    ("C-AGT-SW", "서울서부 대리점", "대리점·도매", "서울", (2,), 1.0, "2013-03-01", None),
    ("C-AGT-GS", "경기남부 대리점", "대리점·도매", "경기", (3,), 1.2, "2012-05-01", None),
    ("C-AGT-GN", "경기북부 대리점", "대리점·도매", "경기", (1,), 0.9, "2014-10-01", None),
    ("C-AGT-CC", "충청 대리점", "대리점·도매", "충청", (2,), 1.1, "2012-05-01", None),
    ("C-AGT-HN", "호남 대리점", "대리점·도매", "호남", (3,), 0.8, "2015-04-01", None),
    ("C-AGT-YN", "영남 대리점", "대리점·도매", "영남", (4,), 1.0, "2016-08-01", None),
    ("C-AGT-GW", "강원 대리점", "대리점·도매", "강원", (4,), 0.5, "2018-02-01", "2025-06-30"),   # 2025년 거래 중지
    ("C-B2B-H01", "가상호텔 청주", "기업·업소", "충청", None, 1.0, "2019-06-01", None),
    ("C-B2B-H02", "가상리조트 단양", "기업·업소", "충청", None, 0.8, "2020-04-01", None),
    ("C-B2B-M01", "가상종합병원 청주", "기업·업소", "충청", None, 1.2, "2019-06-01", None),
    ("C-B2B-M02", "가상요양병원 세종", "기업·업소", "충청", None, 0.6, "2021-02-01", None),
    ("C-B2B-S01", "가상대학교 시설팀", "기업·업소", "충청", None, 1.0, "2019-09-01", None),
    ("C-B2B-S02", "가상학교급식 지원센터", "기업·업소", "충청", None, 0.7, "2020-03-01", None),
    ("C-B2B-F01", "가상빌딩관리 서울", "기업·업소", "서울", None, 1.3, "2019-11-01", None),
    ("C-B2B-F02", "가상물류센터 관리팀", "기업·업소", "경기", None, 0.9, "2021-05-01", None),
    ("C-B2B-C01", "가상전자 복지팀", "기업·업소", "경기", None, 1.1, "2020-01-01", None),
    ("C-B2B-C02", "가상은행 총무팀", "기업·업소", "서울", None, 0.8, "2021-10-01", None),
]


# ---------------------------------------------------------------------------
# 도우미
# ---------------------------------------------------------------------------
def round10(x) -> int:
    return int((Decimal(x) / 10).quantize(Decimal(1), rounding="ROUND_HALF_UP")) * 10


def paper_kg_per_pack(product: str) -> Decimal:
    """원단 무게(kg/팩) = 롤 길이 × 폭 0.1m × 겹수 × 평량(g/m²) × 롤 수 / 1000. 평량은 원단 자재 마스터 값."""
    _, mat, plies, length, rolls, *_ = PRODUCT_SPEC[product]
    gsm = next(m[5] for m in MATERIALS if m[0] == mat)
    return Decimal(length) * ROLL_WIDTH_M * plies * gsm * rolls / 1000


def channel_shares(product: str) -> dict:
    return CHANNEL_SHARE.get(product, GENERAL_CHANNELS)


def price_periods(first_year: int, last_year: int):
    """판매가 적용 기간: (시작일, 종료일 또는 None, 인상 횟수). 매년 3월 1일에 바뀐다."""
    starts = [date(first_year, 1, 1)] + [date(y, 3, 1) for y in range(first_year + 1, last_year + 1)]
    out = []
    for i, s in enumerate(starts):
        end = starts[i + 1] - timedelta(days=1) if i + 1 < len(starts) else None
        out.append((s, end, i))
    return out


def current_list_price(product: str, last_year: int, first_year: int) -> int:
    return round10(Decimal(PRODUCT_SPEC[product][6]) * PRICE_RAISE_RATE ** (last_year - first_year))


# ---------------------------------------------------------------------------
# 테이블 행 만들기
# ---------------------------------------------------------------------------
def supplier_rows():
    return list(SUPPLIERS)


def material_rows():
    return [(c, n, kind, u, plies or "", gsm or "", width or "", sup, u, moq, ss, "Y")
            for c, n, kind, u, plies, gsm, width, sup, moq, ss, _, _ in MATERIALS]


def purchase_price_rows():
    rows = []
    for c, _, kind, u, *_, sup, moq, _, price, lead in MATERIALS:
        index = PAPER_PRICE_INDEX if kind == "원단" else OTHER_PRICE_INDEX
        for i, (start, ratio) in enumerate(index):
            end = ""
            if i + 1 < len(index):
                end = (date.fromisoformat(index[i + 1][0]) - timedelta(days=1)).isoformat()
            unit_price = (Decimal(price) * Decimal(ratio)).quantize(Decimal(1), rounding="ROUND_HALF_UP")
            rows.append((c, sup, int(unit_price), "KRW", u, lead, moq, start, end))
    return rows


def current_material_cost():
    return {m[0]: m[10] for m in MATERIALS}


def product_rows(product_names: dict, safety_stock: dict, first_year: int, last_year: int):
    rows = []
    for code, name in product_names.items():
        brand, mat, plies, length, rolls, box, _, launch = PRODUCT_SPEC[code]
        paper = next(m[2] for m in MATERIALS if m[0] == mat)
        paper_type = "재생펄프" if "재생" in next(m[1] for m in MATERIALS if m[0] == mat) else "천연펄프"
        assert paper == "원단"
        rows.append((code, name, brand, "완제품", paper_type, plies, length, rolls, "EA", box,
                     current_list_price(code, last_year, first_year), launch, "", "판매중", safety_stock[code]))
    return rows


def sales_price_rows(first_year: int, last_year: int):
    rows = []
    for code, spec in PRODUCT_SPEC.items():
        launch = date.fromisoformat(spec[7])
        for channel in channel_shares(code):
            for start, end, raises in price_periods(first_year, last_year):
                if end is not None and end < launch:
                    continue
                price = round10(Decimal(spec[6]) * Decimal(CHANNEL_PRICE_RATE[channel]) * PRICE_RAISE_RATE ** raises)
                rows.append((code, channel, price, max(start, launch).isoformat(), end.isoformat() if end else ""))
    return rows


def customer_rows():
    rows = []
    for c, n, ch, region, days, _, start, end in CUSTOMERS:
        order_days = "/".join("월화수목금토일"[i] for i in days) if days else ("매일" if ch == "온라인" else "수시")
        rows.append((c, n, ch, region, order_days, start, end or "", PAYMENT_TERMS[ch],
                     "거래중지" if end else "거래중", SALES_REP[ch]))
    return rows


class SalesPriceBook:
    """판매 단가표 조회: (제품, 채널, 날짜) → 공급가."""

    def __init__(self, rows):
        self.table = {}
        for code, channel, price, start, end in rows:
            self.table.setdefault((code, channel), []).append(
                (date.fromisoformat(start), date.fromisoformat(end) if end else date.max, price))

    def price(self, product: str, channel: str, d: date) -> int:
        for start, end, price in self.table.get((product, channel), []):
            if start <= d <= end:
                return price
        raise KeyError(f"판매 단가 없음: {product} {channel} {d}")
