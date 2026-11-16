"""문서 종류 분류: 엑셀 한 파일이 BOM / MPS / MRP / RCCP / CRP / MES / ERP 중 무엇인지 판단한다.

업로드 API 의 classify() (등록 대상 테이블 5종 추천)와는 별개의 기능이다. 여기서는 파일을 통째로 받아
"이 문서가 어떤 업무 자료인가"를 본다. 규칙 기반이며 외부 서비스·DB 를 쓰지 않는다.

입력은 시트별 셀 격자(문자열)다. 엑셀을 읽는 일은 호출하는 쪽(tools/sort_folder.py)이 한다.

판단 방식
    1. 시트마다 열 이름 줄을 찾는다(글자 칸이 가장 많은 줄). 그 위쪽은 제목 영역으로 본다.
    2. 제목, 열 이름, 왼쪽 열의 항목 이름에서 범주별 단서 낱말을 찾아 점수를 더한다.
    3. 1순위 점수가 충분하고 2순위와 차이가 날 때만 범주를 정한다. 아니면 '확인 필요'로 남긴다.

점수는 단서 낱말 가중치의 합이며 확률이 아니다. 파일명은 판단에 쓰지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

VERSION = "doctype-0.3.0"
CATEGORIES = ("BOM", "MPS", "MRP", "RCCP", "CRP", "MES", "ERP")
UNKNOWN = "미분류"
MIN_SCORE = 3.0         # 이보다 낮으면 단서가 부족하다고 본다
MIN_MARGIN = 1.5        # 1순위와 2순위 차이가 이보다 작으면 확인 필요
HIGH_SCORE, HIGH_MARGIN = 6.0, 3.0
SCAN_ROWS, SCAN_COLS, HEADER_SEARCH_ROWS, LABEL_COLS = 60, 60, 25, 4

_STRIP = re.compile(r"[\s\[\]\*:()（）_\-./%,·]+")
_NUMBER = re.compile(r"^[+-]?[\d,]*\.?\d+%?$")
_PERIOD = re.compile(r"^(w\d{1,2}|\d{1,2}주차?|\d{4}\d{2}|\d{4}w\d{1,2}|\d{1,2}월|m\d{1,2}|\d{4}\d{2}\d{2}|\d{1,2}\d{2}|\d{2}년\d{1,2}월)$")

# 약어는 낱말 경계를 지켜서 찾는다 ('times' 안의 'mes' 같은 오탐 방지)
ACRONYMS = {"BOM": [("bom", 4.0)], "MPS": [("mps", 4.0), ("atp", 1.5)], "MRP": [("mrp", 4.0)], "RCCP": [("rccp", 4.0)], "CRP": [("crp", 4.0)],
            "MES": [("mes", 4.0), ("oee", 3.0), ("lot", 2.0)], "ERP": [("erp", 3.0)]}
# 정규화한 글자에 포함되는지로 찾는 단서: (낱말, 가중치)
KEYWORDS = {
    "BOM": [("자재명세", 5), ("부품표", 5), ("billofmaterial", 5), ("자품목", 3), ("모품목", 3), ("구성품", 3), ("하위품목", 3), ("상위품목", 2),
            ("component", 3), ("parentitem", 3), ("childitem", 3), ("단위소요량", 3), ("원단위", 3), ("qtyper", 3), ("조달구분", 1.5),
            ("손실률", 1.5), ("스크랩", 1.5), ("scrap", 1.5), ("레벨", 2.5), ("level", 2.5), ("소요수량", 2.5), ("필요량", 1.5), ("조달유형", 1.5),
            ("makebuy", 1.5), ("procurement", 1.5)],
    "MPS": [("주생산계획", 5), ("기준생산계획", 5), ("masterproductionschedule", 5), ("생산계획", 2.5), ("productionplan", 2.5),
            ("plannedproduction", 2.5), ("계획수량", 2), ("planqty", 2), ("확정여부", 1.5), ("납기가능", 1.5), ("수요예측", 1.5), ("forecast", 1.5),
            ("예상재고", 1.5), ("projectedavailable", 1.5), ("생산라인", 1), ("planweek", 1.5), ("계획주차", 1.5), ("계획월", 1), ("확정구분", 1.5),
            ("판매계획", 1.5), ("예측수요", 1.5), ("beginninginventory", 1.5), ("endinginventory", 1.5), ("기초재고", 1), ("기말재고", 1)],
    "MRP": [("자재소요계획", 5), ("materialrequirement", 5), ("총소요", 3), ("순소요", 3), ("예정입고", 3), ("계획발주", 3), ("grossreq", 3),
            ("netreq", 3), ("scheduledreceipt", 3), ("plannedorder", 3), ("계획오더", 2), ("발주예정", 2), ("리드타임", 1.5), ("leadtime", 1.5),
            ("로트사이즈", 1.5), ("lotsize", 1.5), ("가용재고", 1), ("권고", 2), ("부족수량", 2), ("부족량", 2), ("shortage", 2), ("발주계획", 2),
            ("입고예정", 2), ("조달기간", 1.5), ("발주단위", 1.5), ("필요일", 1.5), ("소요일", 1.5), ("needdate", 1.5), ("requireddate", 1.5),
            ("suggestedqty", 2), ("releasedate", 1.5), ("ltdays", 1.5)],
    "RCCP": [("개략능력", 5), ("개략생산능력", 5), ("roughcut", 5), ("주요자원", 3), ("criticalresource", 3), ("keyresource", 3), ("필요시간", 2.5),
             ("requiredhours", 2.5), ("단위당소요시간", 2.5), ("hoursperunit", 2.5), ("제품군", 2), ("productfamily", 2), ("가용시간", 2),
             ("availablehours", 2), ("부하율", 1.5), ("loadrate", 1.5), ("loadpct", 1.5), ("과부족", 1.5), ("가용능력", 2), ("필요능력", 2), ("여유시간", 1.5),
             ("보유시간", 1.5), ("병목", 2), ("소요시간", 1), ("reqhrs", 2.5), ("availhrs", 2), ("stdhrsunit", 2.5), ("overunder", 1.5),
             ("품목군", 2)],
    "CRP": [("능력소요계획", 5), ("capacityrequirement", 5), ("작업장", 3), ("워크센터", 3), ("workcenter", 3), ("오더부하", 3), ("orderload", 3),
            ("준비시간", 2.5), ("setuptime", 2.5), ("가공시간", 2.5), ("runtime", 2.5), ("공정순번", 2), ("operationseq", 2), ("가용능력", 2),
            ("availablecapacity", 2), ("공정명", 1.5), ("부하율", 1.5), ("loadrate", 1.5), ("착수일", 1.5), ("작업지시", 1), ("workorder", 1),
            ("작업센터", 3), ("opseq", 2), ("공정번호", 2), ("setuphrs", 2.5), ("셋업", 2.5), ("runhrs", 2.5), ("loadhours", 2), ("부하시간", 2),
            ("제조오더", 1.5), ("소요시간", 1), ("소요능력", 2), ("utilization", 1.5), ("plannedload", 3), ("releasedload", 3), ("totalload", 2),
            ("부하합계", 2), ("총부하", 2)],
    "MES": [("제조실행", 5), ("작업일보", 4), ("생산실적", 3), ("작업실적", 3), ("비가동", 3), ("downtime", 3), ("양품", 2.5), ("goodqty", 2.5),
            ("실적수량", 2.5), ("불량", 2), ("defect", 2), ("가동시간", 2), ("가동률", 2), ("로트", 1.5), ("작업자", 1.5), ("operator", 1.5),
            ("시작시각", 1.5), ("종료시각", 1.5), ("starttime", 1.5), ("endtime", 1.5), ("검사", 1), ("설비코드", 1), ("작업지시", 1), ("workorder", 1),
            ("투입", 1.5), ("inputqty", 1.5), ("inputtime", 1.5), ("정지시간", 2.5), ("정지사유", 2.5), ("stophrs", 2.5), ("stopreason", 2.5),
            ("운전시간", 2), ("operatinghrs", 2), ("runhours", 2), ("availability", 1.5), ("합격수량", 2.5), ("부적합", 2), ("ngqty", 2),
            ("ngtype", 2), ("inspect", 1), ("shopfloor", 4), ("호기", 1), ("machine", 1), ("disposition", 1.5), ("결함", 2)],
    "ERP": [("거래처", 2.5), ("공급사", 2.5), ("supplier", 2.5), ("vendor", 2.5), ("수주", 2.5), ("주문번호", 2.5), ("salesorder", 2.5),
            ("발주번호", 2.5), ("pono", 2.5), ("purchaseorder", 2.5), ("입고번호", 2.5), ("고객사", 2), ("customer", 2), ("orderno", 2), ("단가", 2),
            ("unitprice", 2), ("결제조건", 2), ("paymentterm", 2), ("현재고", 2), ("onhand", 2), ("안전재고", 2), ("safetystock", 2),
            ("제품유형", 2), ("세금계산서", 2), ("금액", 1.5), ("amount", 1.5), ("자재구분", 1.5), ("창고", 1), ("제품명", 0.5), ("자재명", 0.5),
            ("제품구분", 2), ("producttype", 2), ("적정재고", 2), ("판매상태", 1.5), ("정가", 1.5), ("판매가", 1.5), ("listprice", 1.5),
            ("price", 1.5), ("통화", 1.5), ("currency", 1.5), ("적용시작일", 1), ("validfrom", 1), ("채널", 1), ("channel", 1), ("제품코드", 1),
            ("productcode", 1), ("자재유형", 1.5), ("materialtype", 1.5), ("moq", 1.5), ("최소주문량", 1.5), ("업체", 1.5), ("할당재고", 1.5),
            ("allocated", 1.5), ("stockqty", 2), ("재고수량", 2), ("실재고", 2), ("납품기간", 1.5), ("deliverydays", 1.5), ("grno", 2),
            ("receiptno", 2.5), ("receiptqty", 2), ("입고수량", 2), ("masterdata", 3), ("기준정보", 3)],
}
# 정확히 그 낱말일 때만 인정하는 단서 (다른 낱말의 일부로 자주 나오는 것)
EXACT = {"BOM": [("소요량", 3), ("lv", 2.5), ("qty", 0.5)], "MPS": [("firm", 1.5), ("line", 1), ("라인", 1)], "MRP": [("lt", 1.5)],
         "RCCP": [("설비", 1.5), ("자원", 1.5), ("설비명", 1), ("자원명", 1), ("자원코드", 1.5), ("resource", 1.5), ("resourcename", 1)],
         "CRP": [("wc", 2), ("operation", 1.5), ("공정", 1.5), ("wcname", 2)], "MES": [("lotno", 2)], "ERP": [("sku", 1.5)]}
# doctype-0.3.0: 실제 문서 형태(더미 v2)의 dev 분할에서 놓친 사례를 보고 더한 단서.
# 영문 시스템 표기(Oracle·SAP·교재)와 국내 수작업 서식의 낱말이 처음에는 거의 없었다.
_MORE = {
    "BOM": [("upperpart", 3), ("lowerpart", 3), ("parentpart", 3), ("childpart", 3), ("productstructure", 4), ("정미수량", 3), ("자품번", 3),
            ("모품번", 3), ("구성표", 3), ("필요수량", 2), ("componentnumber", 3), ("compqty", 3)],
    "MPS": [("firmplannedorder", 2), ("netdemand", 1.5), ("customerorder", 2), ("availabletopromise", 2.5), ("projectedavailablebalance", 2.5),
            ("masterschedule", 1.5), ("demandforecast", 1), ("ratenddate", 1.5), ("rateenddate", 1.5), ("dailyquantity", 1.5), ("scheduledate", 1.5),
            ("생산일정", 2.5), ("일자별계획", 2)],
    "MRP": [("mrpelement", 4), ("reschedulingdate", 2), ("receiptreqmt", 2.5), ("availableqty", 1.5), ("projectedonhand", 2.5), ("lowlevelcode", 2),
            ("plannedorderreceipt", 1), ("plannedorderrelease", 1), ("보유재고", 1.5), ("기발주", 2.5), ("할당량", 1.5), ("소요량전개", 4),
            ("소요량산출", 4), ("발주예정량", 2), ("mrptype", 2), ("mrparea", 2)],
    "RCCP": [("billofresource", 4), ("billsofresource", 4), ("masterschedule", 1.5), ("setbackdays", 2), ("reqdhrs", 2), ("totalhrs", 1),
             ("loadratio", 2.5), ("weekstartdate", 1), ("usageqty", 1), ("개략", 3), ("보유공수", 2), ("보유능력", 2), ("소요공수", 1.5),
             ("소요능력", 1.5), ("공수검토", 3)],
    "CRP": [("capload", 3), ("availcap", 2.5), ("remavailcap", 2.5), ("capacitycat", 2), ("capacityplanning", 2), ("setupreqmts", 2.5),
            ("procreqmts", 2.5), ("earlstart", 1.5), ("latestfinish", 1.5), ("requirements", 1), ("소요공수", 1.5), ("공정순서", 2), ("착수예정", 1.5),
            ("완료예정", 1)],
    "MES": [("정품", 2.5), ("생산현황", 3), ("생산일지", 4), ("생산일보", 4), ("작업인원", 1.5), ("불량률", 1.5), ("불량율", 1.5), ("불량원인", 1.5),
            ("불량사유", 1.5), ("불량품", 2), ("개선대책", 1.5), ("생산량", 1.5), ("품질", 1.5), ("부하시간", 1), ("성능가동률", 3), ("시간가동률", 3),
            ("양품률", 2), ("설비종합효율", 4), ("confirmation", 2), ("postingdate", 1.5), ("enteredby", 1), ("workcenter", 1), ("confirmedyield", 2)],
    "ERP": [("address", 1.5), ("contactperson", 1.5), ("payment", 1.5), ("creditline", 2), ("rating", 1), ("liabilitylimit", 1.5), ("inventory", 2),
            ("reservedstock", 2), ("reorderlevel", 2), ("openorder", 1.5), ("stock", 1), ("계정구분", 2), ("재고단위", 1.5), ("품목등록", 3),
            ("사용여부", 1), ("조달구분", 1), ("조회기간", 1.5), ("사업장", 1), ("출력일시", 1), ("수불", 3), ("기초수량", 1.5), ("출고수량", 1.5),
            ("공급가액", 2), ("부가세", 2), ("발주일자", 1.5), ("수주일자", 1.5), ("전표", 1.5)],
}
_MORE_EXACT = {"BOM": [("level", 2.5), ("레벨", 2.5), ("structure", 1.5)], "MES": [("yield", 2.5), ("scrap", 1.5), ("결과", 0.5)],
               "RCCP": [("department", 1), ("dept", 1), ("res", 1), ("basis", 1)], "CRP": [("week", 0.5)]}
# 다른 낱말의 일부로 잘못 잡히던 것을 고친다: (범주, 낱말) -> 새 가중치. 0 이면 뺀다.
_REWEIGHT = {("BOM", "level"): 0, ("BOM", "레벨"): 0,                      # 'Reorder level' 을 BOM 으로 보던 문제 → 정확히 일치할 때만
             ("MES", "shopfloor"): 2,                                      # 'Shop-floor stock' 은 재고 구분이다
             ("CRP", "workcenter"): 2, ("ERP", "safetystock"): 1, ("ERP", "안전재고"): 1, ("ERP", "allocated"): 1, ("ERP", "할당재고"): 1}
for _cat in KEYWORDS:
    KEYWORDS[_cat] = [(w, _REWEIGHT.get((_cat, w), wt)) for w, wt in KEYWORDS[_cat] if _REWEIGHT.get((_cat, w), wt) > 0] + _MORE.get(_cat, [])
    EXACT[_cat] = EXACT[_cat] + _MORE_EXACT.get(_cat, [])

ERP_SUBTYPES = [("수주", ("수주", "주문번호", "salesorder", "orderno")), ("발주", ("발주번호", "pono", "purchaseorder")), ("입고", ("입고번호",)),
                ("재고", ("현재고", "onhand")), ("단가표", ("단가", "unitprice")), ("거래처", ("거래처", "고객사", "customer")),
                ("공급사", ("공급사", "supplier", "vendor")), ("제품 마스터", ("제품유형", "제품명")), ("자재 마스터", ("자재구분", "자재명"))]


def norm(text) -> str:
    return _STRIP.sub("", str(text).lower()) if text is not None else ""


@dataclass
class Verdict:
    category: str                       # 7개 범주 중 하나 또는 '미분류'
    needs_review: bool                  # 사람이 확인해야 하는가
    confidence: str                     # 높음 / 보통 / 낮음
    score: float
    runner_up: str | None = None
    runner_up_score: float = 0.0
    detail: str = ""                    # ERP 세부 종류 등
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    scores: dict[str, float] = field(default_factory=dict)


def _is_text(cell: str) -> bool:
    return bool(cell) and not _NUMBER.match(cell.replace(" ", ""))


def _collect(rows: list[list]) -> tuple[list[str], int]:
    """시트에서 판단에 쓸 글자(제목, 열 이름, 왼쪽 열의 항목 이름)를 모은다. 열 이름 줄을 찾지 못하면 빈 목록."""
    grid = [[("" if c is None else str(c).strip()) for c in row[:SCAN_COLS]] for row in rows[:SCAN_ROWS]]
    best, best_count = -1, 0
    for i, row in enumerate(grid[:HEADER_SEARCH_ROWS]):
        count = sum(1 for c in row if _is_text(c) and len(c) <= 40)
        if count > best_count:
            best, best_count = i, count
    if best < 0 or best_count < 2:
        return [c for row in grid[:HEADER_SEARCH_ROWS] for c in row if _is_text(c)], 0
    header = grid[best]
    first = next((j for j, c in enumerate(header) if c), 0)
    texts = [c for row in grid[:best] for c in row if _is_text(c)]              # 제목 영역
    texts += [c for c in header if c]
    for row in grid[best + 1:]:                                                 # 항목 이름이 세로로 놓인 표
        texts += [c for c in row[first:first + LABEL_COLS] if _is_text(c) and len(c) <= 40]
    period_cells = [norm(c) for c in header if _PERIOD.match(norm(c))]
    monthly = sum(1 for c in period_cells if "월" in c or re.match(r"^\d{6}$|^m\d", c))
    if len(period_cells) >= 3:
        texts.append("__wide_monthly__" if monthly >= len(period_cells) / 2 else "__wide_weekly__")
    return texts, len(period_cells)


def score_texts(texts: list[str]) -> tuple[dict[str, float], dict[str, list[str]]]:
    raw = " ".join(t.lower() for t in texts)
    keys = {norm(t) for t in texts} - {""}
    scores, evidence = {}, {}
    for cat in CATEGORIES:
        total, found = 0.0, []
        for word, weight in ACRONYMS[cat]:
            if re.search(rf"(?<![a-z]){word}(?![a-z])", raw):
                total += weight
                found.append(word.upper())
        for word, weight in KEYWORDS[cat]:
            if any(word in k for k in keys):
                total += weight
                found.append(word)
        for word, weight in EXACT[cat]:
            if word in keys:
                total += weight
                found.append(word)
        scores[cat], evidence[cat] = total, found
    # 기간이 가로로 놓인 격자는 계획 문서다. 기준정보·거래 목록(ERP)일 가능성은 낮게 본다
    if ("widemonthly" in keys or "wideweekly" in keys) and scores["ERP"] > 0:
        scores["ERP"] = round(scores["ERP"] * 0.5, 2)
    # RCCP 는 MPS 를 기준으로 계산하므로 문서에 'MPS' 가 언급된다. 능력 단서가 충분하면 그 언급만으로 MPS 로 보지 않는다
    if scores["RCCP"] >= MIN_SCORE and set(evidence["MPS"]) <= {"MPS", "masterschedule", "scheduledate"}:
        scores["MPS"] = 0.0
    # 부하·능력 표에서만 기간 단위를 본다: 월 단위면 개략(RCCP), 주·일 단위면 상세(CRP) 쪽으로 조금 기운다
    if scores["RCCP"] > 0 and scores["CRP"] > 0:
        if "widemonthly" in keys:
            scores["RCCP"] += 1.5
            evidence["RCCP"].append("월 단위 기간")
        elif "wideweekly" in keys:
            scores["CRP"] += 1.0
            evidence["CRP"].append("주·일 단위 기간")
    return scores, evidence


def classify_workbook(sheets: list[tuple[str | None, list[list]]]) -> Verdict:
    """sheets: (시트 이름, 행 목록). 행은 셀 값 목록이다."""
    totals = {c: 0.0 for c in CATEGORIES}
    evidence = {c: [] for c in CATEGORIES}
    any_text, wide = False, False
    for _, rows in sheets:
        texts, n_periods = _collect(rows)
        wide = wide or n_periods >= 3
        any_text = any_text or bool(texts)
        scores, found = score_texts(texts)
        for cat in CATEGORIES:                      # 시트별 점수 중 가장 큰 값을 쓴다 (표지·안내 시트가 결과를 흐리지 않도록)
            if scores[cat] > totals[cat]:
                totals[cat], evidence[cat] = scores[cat], found[cat]
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    (top, top_score), (second, second_score) = ranked[0], ranked[1]
    base = {"score": round(top_score, 2), "runner_up": second if second_score > 0 else None, "runner_up_score": round(second_score, 2),
            "scores": {k: round(v, 2) for k, v in totals.items()}}
    if not any_text:
        return Verdict(UNKNOWN, True, "낮음", 0.0, reason="읽을 수 있는 글자가 없습니다.", scores=base["scores"])
    if top_score < MIN_SCORE and wide:
        return Verdict(UNKNOWN, True, "낮음", **{k: base[k] for k in ("score", "runner_up", "runner_up_score", "scores")},
                       reason="기간이 가로로 놓인 수량표입니다. 제목이나 항목 이름이 없어 MPS·수요예측·출하계획 중 무엇인지 알 수 없습니다.")
    if top_score < MIN_SCORE:
        return Verdict(UNKNOWN, False, "보통" if top_score == 0 else "낮음", **{k: base[k] for k in ("score", "runner_up", "runner_up_score", "scores")},
                       evidence=evidence[top] if top_score else [],
                       reason="일곱 범주의 단서 낱말을 찾지 못했습니다." if top_score == 0 else f"{top} 단서가 조금 있지만 부족합니다.")
    detail = ""
    if top == "ERP":
        keys = evidence["ERP"]
        detail = next((name for name, words in ERP_SUBTYPES if any(w in keys for w in words)), "")
    if top_score - second_score < MIN_MARGIN:
        return Verdict(top, True, "낮음", **{k: base[k] for k in ("score", "runner_up", "runner_up_score", "scores")}, detail=detail,
                       evidence=evidence[top], reason=f"{top}와 {second}의 단서가 함께 있어 확인이 필요합니다.")
    high = top_score >= HIGH_SCORE and top_score - second_score >= HIGH_MARGIN
    return Verdict(top, False, "높음" if high else "보통", **{k: base[k] for k in ("score", "runner_up", "runner_up_score", "scores")}, detail=detail,
                   evidence=evidence[top], reason=f"{top} 단서: {', '.join(evidence[top][:6])}")
