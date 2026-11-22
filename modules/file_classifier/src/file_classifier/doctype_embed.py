"""선택 기능: 낱말 단위 의미 매칭으로 문서 종류를 추정한다 (규칙 doctype.py 를 보완).

규칙은 낱말 사전이라 처음 보는 표기를 만나면 미분류로 빠진다. 여기서는 파일의 낱말(제목, 열 이름, 항목 이름)
하나하나를 임베딩해서 범주별 기준 용어 중 뜻이 가장 가까운 것에 연결한다. '정품수량'은 사전에 없어도
'양품 수량'에 가깝다고 보고 MES 쪽 단서로 센다.

쓰임새 (combine):
    - 규칙이 범주를 정하지 못한 파일은 의미 매칭 결과를 쓴다.
    - 규칙과 의미 매칭이 서로 다른 범주를 내면 어느 쪽도 믿지 않고 '확인 필요'로 돌린다.

torch 와 transformers 가 필요하다(이 모듈을 import 하지 않으면 필요 없다). 모델은 BAAI/bge-m3 이고 로컬에서만
돈다. 파일 내용을 외부로 보내지 않는다. 유사도와 점수는 확률이 아니다.

시도했지만 효과가 없어 뺀 방식: 파일 전체를 한 문장으로 임베딩해 범주 설명과 비교, 정답을 아는 예시 파일과의
최근접 이웃(kNN). 둘 다 처음 보는 형태에서 대부분 '확인 필요'로 빠졌다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .doctype import UNKNOWN, Verdict, _collect

MODEL = "BAAI/bge-m3"
VERSION = "doctype-embed-0.2.0"
MAX_TERMS = 90          # 파일 하나에서 보는 낱말 수 상한
TAU = 0.65              # 낱말과 기준 용어의 유사도가 이 이상일 때만 단서로 센다
MIN_SCORE = 1.5         # 범주 점수(연결된 기준 용어들의 유사도 합)가 이 이상이어야 한다
MIN_MARGIN = 0.6        # 1순위와 2순위 점수 차이
# 범주별 기준 용어. 특정 더미 파일의 열 이름이 아니라 업무에서 통용되는 용어로 골랐다.
CONCEPTS = {
    "BOM": ["모품목", "자품목", "구성품", "하위 품목", "상위 품목", "단위 소요량", "BOM 레벨", "손실률", "자재명세서", "parent item", "component",
            "child part", "quantity per", "bill of materials", "product structure", "scrap rate"],
    "MPS": ["주생산계획", "기준생산계획", "생산 계획 수량", "수요 예측", "고객 주문", "예상 가용 재고", "납기 약속 가능 수량", "master production schedule",
            "demand forecast", "customer orders", "projected available balance", "available to promise", "firm planned order"],
    "MRP": ["자재소요계획", "총소요량", "순소요량", "예정 입고", "계획 발주", "발주 예정일", "리드타임", "로트 크기", "소요량 전개", "gross requirements",
            "net requirements", "scheduled receipts", "planned order release", "projected on hand", "MRP element", "lead time"],
    "RCCP": ["개략능력계획", "주요 자원", "병목 설비", "필요 시간", "가용 시간", "부하율", "보유 공수", "소요 공수", "rough-cut capacity planning",
             "bill of resources", "required hours", "available hours", "load ratio", "key resource", "master schedule quantity"],
    "CRP": ["능력소요계획", "작업장", "공정 순서", "준비 시간", "가공 시간", "작업장 부하", "가용 능력", "작업지시 부하", "capacity requirements planning",
            "work center", "setup time", "run time", "capacity load", "available capacity", "remaining capacity", "operation sequence"],
    "MES": ["생산 실적", "작업일보", "양품 수량", "불량 수량", "불량 사유", "작업자", "설비 가동 시간", "설비 정지 시간", "가동률", "LOT 번호", "검사 결과",
            "production result", "good quantity", "defect quantity", "scrap quantity", "operator", "machine downtime", "OEE", "lot number",
            "inspection result", "confirmed yield"],
    "ERP": ["거래처", "공급사", "수주 번호", "발주 번호", "입고 번호", "단가", "공급가액", "재고 수량", "안전 재고", "품목 마스터", "결제 조건", "customer",
            "supplier", "sales order", "purchase order", "unit price", "amount", "stock on hand", "safety stock", "payment terms", "item master"],
    # 제조 계획과 무관한 문서의 용어. 여기에 더 가까우면 미분류로 본다 (예: '점검 결과'를 MES 의 '검사 결과'로 보는 오탐 방지)
    UNKNOWN: ["사원 번호", "성명", "부서", "직급", "입사일", "출근 시각", "퇴근 시각", "회의 안건", "결정 사항", "설문 응답", "만족도", "교육 과정", "강사",
              "차량 번호", "운전자", "주행 거리", "에너지 사용량", "요금", "안전 점검", "점검 항목", "점검자", "비상 연락처", "사무용품 신청",
              "employee", "attendance", "meeting minutes", "survey response", "training course", "vehicle log", "utility cost", "safety checklist"],
}
REVIEW = "확인 필요"
COMMON = "공통"
# 어느 문서에나 나오는 낱말. 여기에 가장 가까운 낱말은 어느 범주의 단서로도 세지 않는다.
# 이 묶음이 없으면 '자재코드', '품목명', '단위' 같은 흔한 열 이름이 뜻이 비슷한 BOM 용어('자재명세서', '자품목', '단위 소요량')에 붙어,
# 자재 목록이나 재고 자료가 BOM 으로 분류된다 (팀원이 만든 자료로 시험해 확인한 오분류).
CONCEPTS[COMMON] = ["품목 코드", "품목명", "품목 구분", "자재 코드", "자재명", "자재 구분", "제품 코드", "제품명", "제품", "자재", "원자재", "부자재",
                    "단위", "수량", "규격", "구분", "비고", "일자", "번호", "코드", "이름", "사용 여부",
                    "item code", "item name", "item type", "material code", "material name", "material", "product code", "product name", "product",
                    "unit", "quantity", "specification", "remarks", "date", "number", "code", "name", "type", "status", "period", "currency"]


@dataclass
class SemanticResult:
    category: str | None                                # 범주, '미분류', 또는 None(확인 필요)
    scores: dict[str, float] = field(default_factory=dict)
    matches: list[str] = field(default_factory=list)    # "파일 낱말 ≈ 기준 용어" 근거


def workbook_terms(sheets: list[tuple[str | None, list[list]]]) -> list[str]:
    """파일에서 뜻을 담은 낱말만 뽑는다 (제목, 열 이름, 항목 이름. 중복 제거, 순서 유지)."""
    seen, items = set(), []
    for _, rows in sheets:
        texts, _ = _collect(rows)
        for t in texts:
            t = str(t).strip()
            if t and not t.startswith("__") and t not in seen and len(t) <= 60:
                seen.add(t)
                items.append(t)
    return items[:MAX_TERMS]


class Embedder:
    """BGE-M3 dense 임베딩 (CLS, L2 정규화)."""

    def __init__(self, device: str | None = None):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tok = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModel.from_pretrained(MODEL).eval().to(self.device)
        if self.device == "cuda":
            self.model.half()

    def encode(self, texts: list[str], batch_size: int = 64):
        import numpy as np

        out = []
        with self.torch.no_grad():
            for i in range(0, len(texts), batch_size):
                enc = self.tok(texts[i:i + batch_size], padding=True, truncation=True, max_length=64, return_tensors="pt").to(self.device)
                hidden = self.model(**enc).last_hidden_state[:, 0]
                out.append(self.torch.nn.functional.normalize(hidden.float(), dim=-1).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, 1024), dtype="float32")


class SemanticMatcher:
    def __init__(self, embedder: Embedder | None = None, tau: float = TAU, min_score: float = MIN_SCORE, min_margin: float = MIN_MARGIN):
        self.embedder = embedder or Embedder()
        self.tau, self.min_score, self.min_margin = tau, min_score, min_margin
        self.concepts = [(cat, term) for cat, terms in CONCEPTS.items() for term in terms]
        self.concept_vectors = self.embedder.encode([term for _, term in self.concepts])
        self._cache: dict[str, object] = {}

    def _vectors(self, terms: list[str]):
        missing = [t for t in terms if t not in self._cache]
        if missing:
            for t, v in zip(missing, self.embedder.encode(missing)):
                self._cache[t] = v
        return [self._cache[t] for t in terms]

    def classify(self, sheets: list[tuple[str | None, list[list]]]) -> SemanticResult:
        terms = workbook_terms(sheets)
        best: dict[tuple[str, str], tuple[float, str]] = {}
        for term, vec in zip(terms, self._vectors(terms)):
            sims = self.concept_vectors @ vec
            j = int(sims.argmax())
            if self.concepts[j][0] == COMMON:
                continue
            if sims[j] >= self.tau and float(sims[j]) > best.get(self.concepts[j], (0.0, ""))[0]:
                best[self.concepts[j]] = (float(sims[j]), term)          # 기준 용어 하나는 한 번만 센다
        scores: dict[str, float] = {}
        for (cat, _), (sim, _) in best.items():
            scores[cat] = round(scores.get(cat, 0.0) + sim, 3)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1]) + [("", 0.0), ("", 0.0)]
        (top, s1), (_, s2) = ranked[0], ranked[1]
        matches = [f"{term} ≈ {concept}" for (cat, concept), (_, term) in sorted(best.items(), key=lambda kv: -kv[1][0]) if cat == top][:6]
        if not top or s1 < self.min_score:
            return SemanticResult(UNKNOWN, scores, [])
        return SemanticResult(top if s1 - s2 >= self.min_margin else None, scores, matches)


def combine(verdict: Verdict, semantic: SemanticResult) -> tuple[str, str]:
    """규칙 결과와 의미 매칭 결과를 합쳐 (결과 표에 적을 분류, 이유) 를 돌려준다."""
    rule = REVIEW if verdict.needs_review else verdict.category
    sem = REVIEW if semantic.category is None else semantic.category
    near = ", ".join(semantic.matches[:4])
    if rule in (UNKNOWN, REVIEW):
        if sem in (UNKNOWN, REVIEW):
            return (REVIEW if REVIEW in (rule, sem) else UNKNOWN), verdict.reason
        return sem, f"규칙은 정하지 못했고, 뜻이 가까운 낱말로 {sem} 로 판단: {near}"
    if sem not in (UNKNOWN, REVIEW, rule):
        return REVIEW, f"규칙은 {rule}, 의미 매칭은 {sem} 로 달라 확인이 필요합니다 ({near})"
    return rule, verdict.reason
