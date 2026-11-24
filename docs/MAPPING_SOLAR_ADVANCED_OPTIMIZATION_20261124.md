# 제조업 스키마 매핑 · Phase 9 평가 준비와 승인 계획

2026-11-24 KST · Windows 메인 PC CPU · 김대영 · 기준 [5dec94b](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5dec94b2232550dfcb1346bb2f5ece225d643e9f)

## 목적과 선행 근거

Phase 8의 두 합성 문서에서 Mini 4와 Pro 4 직접 매핑은 Phase 5·6과 동일한 21정답·0오추천이었다. 이번에는 처음 보는 양식에서 검색 누락, 역할 혼동, 과다 HOLD와 중복 대상을 분리한다. 성능 목표는 직접 매핑 정답 대비 정확 추천율 ≥90%, 추천 정밀도 ≥98%, 전체 열 오추천율 ≤1%, 보류 정답 거절률 ≥98%, 계약 영향 문서율 ≤1%다. 완전 매핑·필수 필드·수동 수정 열도 별도로 비교한다. [Phase 8 실측](MAPPING_SOLAR_PHASE8_20261124.md)

이전 실험의 검색기·보정·게이트는 기존 결과를 기준선으로 재사용한다. 동일 응답 캐시는 요청 지문이 일치할 때만 재생한다. [종합](MAPPING_COMPREHENSIVE_RESEARCH_20261124.md) · [아키텍처](MAPPING_FINAL_ARCHITECTURE_EVALUATION_20261124.md) · [Phase 5](MAPPING_ACCURACY_OPTIMIZATION_20261124.md) · [Phase 6](MAPPING_RESEARCH_PAPER_BENCHMARK_20261124.md) · [Phase 7](MAPPING_LLM_PAPER_OPTIMIZATION_20261124.md)

## 데이터 동결

`scripts/mapping_phase9_data.py`는 고정 시드로만 값을 생성한다. 제품, 자재, BOM, 재고, 월별 수요의 스키마를 모두 포함한다. 정규 열, 비표준 한·영 열, 업무 역할 혼합, 정수처럼 보이는 발주·반품·안전재고, BOM 기준 산출·투입·손실, 거래일·귀속 월, 거래처 코드·제품 코드, 별도 변환이 필요한 날짜·백분율을 포함했다. 재고 표에서는 행별 현재고가 할당재고와 가용재고의 합이 되도록 구성했다. 명시적 변환 필요 열에는 의미 정답을 부여하고 직접 매핑 정답은 비워 두었다.

| 합성 분할 | 문서 | 양식군 | 직접 매핑 | HOLD | 변환 필요 | SHA-256 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Selection | 50 | 25 | 326 | 140 | 4 | `1261f5a31baee9850b3d768523faa21fed0485232a2522c2836b455878b26905` |
| Risk | 50 | 25 | 326 | 140 | 4 | `ab6f993caae1817a99a3c50d4de8563db07597be05b35241eb8f3c2009684aba` |
| Holdout | 200 | 50 | 1,304 | 560 | 16 | `072aa3c14d6a29c95ecfebce64b69eb0c34ed9c3e10e39a9d2eca1db10f814a1` |

원본 CSV 해시, 양식군과 비표준 정규화 헤더의 분할 중복을 검사했다. 등록 스키마에 있는 표준 헤더는 여러 분할에서 정규 대조군으로 사용한다. 양식군은 분리했지만 생성기는 같은 업무 개념과 값 구조를 공유하므로 결과 해석은 이 합성 분포로 제한한다. Risk와 Holdout은 데이터 SHA만 동결했다. Holdout으로 점수, 사례, 추천 후보를 열어 보거나 프롬프트를 선택하지 않은 상태다. 최종 평가 전에 모델, 정책, 프롬프트, 예시 조회와 임곗값도 별도로 동결한다.

## 9-A · 동일 Selection의 로컬 기준선

| 기준선 | 정답 / 326 | 오추천 / 470 | HOLD | 추천 정밀도 | 직접 매핑 정확 추천율 | 필수 정답 / 248 | 완전 매핑 / 50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Exact/RapidFuzz | 66 | 0 | 404 | 100.00% | 20.25% | 50 | 10 |
| Phase 5 | 135 | 2 | 333 | 98.54% | 41.41% | 90 | 10 |
| Phase 6 | 147 | 0 | 323 | 100.00% | 45.09% | 102 | 10 |

Phase 6은 원시 Top-3에서 310개 정답을 찾았고 직접 매핑 정답 179개를 HOLD했다. 전체 오추천율 0%, 정상 HOLD·변환 필요의 거절률 100%를 기록했다. 정확 추천율이 목표에 미달한다. Phase 5의 두 오추천은 BOM 행 번호를 자재 소요량으로 판정한 사례다. 기존 정상 추천 보존, Top-3 밖 16개 정답의 복원, 후보에 있는 보류 열의 복원을 따로 집계한다.

### 신규 외부 전송 승인 범위

승인 대상 SHA-256은 **`3d3b72941df49ce72e13e545143c92801004c78050d4ec934d2c041e9f2525f3`**다. `https://api.upstage.ai/v1/chat/completions`에서 Mini 4 `solar-mini4-260922`와 Pro 4 `solar-pro4-260806` 스냅샷을 사용한다. 두 모델 ID와 보수적인 입력·출력 백만 토큰당 Mini USD 0.10/0.40, Pro USD 0.30/1.20 기준을 공식 문서에서 대조했다. Preview는 요청 계획에 포함하지 않았다. [Chat 스냅샷 목록](https://console.upstage.ai/api/chat) · [공개 요금](https://www.upstage.ai/pricing/api)

| 요청 | 문서 수 | 최대 호출 | 최대 예약액 (USD) |
| --- | ---: | ---: | ---: |
| Mini 4 직접 매핑·독립 Typed 판정 | 50 | 100 | 0.13174040 |
| Pro 4 직접 매핑 | 50 | 50 | 0.13878810 |
| 합계 | 50 | **150** | **0.27052850** |

입력 토큰 대용치 상한은 1,443,810, 출력 토큰 상한은 43,600이다. 본문 바이트에 건당 512를 더해 입력 사용량을 보수적으로 잡고 VAT 10%를 계산했다. 실제 청구액은 응답 사용량과 공급사 자료로 확인해야 한다. Phase 8의 Mini·Pro 직접 및 Mini Typed 평균을 50문서에 단순 환산하면 USD 0.072655이지만, Phase 9의 더 긴 입력과 다른 검증 프롬프트를 반영하지 못하므로 예약액에 적용하지 않는다.

호출 150개는 신규 **Selection 50문서**의 제목·열 이름·열당 합성 값 최대 3개, 표준 스키마·업무 정의·파생 자료형·관계·대조 증거·후보 순서와 작업 ID만 보낸다. 정답, 학습 예시, Risk·Holdout, 디스크 원본과 실제 기업 자료는 계획에 포함하지 않았다. 키는 무시된 로컬 파일에서 읽어 서비스 인증에 사용하고, 본문·문서·원장에는 저장하지 않는다. 실행기는 현재 원장 SHA와 잠금, 별도의 정확한 계획 승인, 요청별 본문 SHA, 모델 및 금액을 확인한다.

Mini·Pro 각각의 직접 응답을 계약 검사 후 원시 추천과 기존 로컬 유일성·직접 등록 가능 검사 적용안으로 나눠 채점한다. 같은 Mini Typed 응답을 고정밀 로컬 합의의 HOLD 복원, 전체 Phase 6 추천의 독립 검증에 공용으로 사용한다. 판정 프롬프트는 기존 답을 명시하지 않는다. 네트워크 응답이 없는 로컬 기준선, 재사용 응답, 실제 신규 응답의 비용·처리시간을 구분한다.

## 9-B~E · 실행 순서와 예산

| 단계 | 먼저 검증할 범위 | 초기 배정 한도 (USD) | 현재 상한 산식 |
| --- | --- | ---: | --- |
| A | Selection 50문서, 로컬 3·Solar 파생 6 비교 | 1.00 | 요청별 SHA로 고정한 150회 / 0.27052850 |
| B | Selection 어려운 양식 부분집합, 이득이 있는 방식만 확대 | 2.00 | Mini 240 + Pro 40회 이내 / 1.16867520 |
| C | Train·Development 컴파일과 같은 평가 조건 비교 | 3.00 | Mini 컴파일 300회 / 0.84268800과 Mini 평가 100 + Pro 30회 / 0.61680080 |
| D | 조합 및 소거 실험, 독립 Risk 보정 | 1.50 | Mini 150 + Pro 50회 이내 / 0.97389600 |
| E | 확정 정책의 200문서 독립 평가 | 2.00 | Mini 200 + Pro 선택 최대 100회 / 1.62316000 |
| 예비비 | 별도 확인 후 사용 | 0.57932363 | 단계 상한과 중복 예약하지 않음 |

A는 별도 전송 승인 대기 중이다. B~E 추정치는 요청·분할·비용을 나중에 서명하기 위한 상한으로, 합성 학습 예시·옵티마이저 reflection·Risk·Holdout 외부 전송을 각각 승인받는다. B~E는 본문 24,000바이트, 건당 512 대용 토큰 여유와 출력 1,250토큰을 예시 상한으로 썼다. C 컴파일은 출력 256토큰을 적용했다. 기존 공용 원장 계산액 **USD 2.03807637**, 미확정 예약액 **USD 7.88260000**, 누적 **USD 9.92067637**와 응답 캐시를 보존했다. 누적 한도 USD 20에서 신규 예약 여유는 **USD 10.07932363**이다.

1. **B01~B04.** Matchmaker는 독립 후보·합집합·정제·절대 신뢰도와 동적 합성 예시, JevNexus는 후보별 Typed 판정과 불일치·낮은 여유에서 선택적 Listwise, ConStruM은 기존 혼동군과 열 문맥을 제한된 근거 팩으로 만들기, Magneto는 동일 후보에서 Pointwise·Pairwise·Listwise·순서 반전 합의를 비교한다. Phase 7 코드의 구현을 재사용하며 JevNexus 원 논문의 로짓 결합과 ConStruM의 전체 하이퍼그래프는 별도의 구현 범위다. [Matchmaker](https://arxiv.org/abs/2410.24105) · [JevNexus 및 코드](https://arxiv.org/abs/2610.09487) · [ConStruM v3](https://arxiv.org/abs/2601.20482v3) · [Magneto 구현](https://github.com/VIDA-NYU/magneto-matcher)
2. **B05~B07.** `mapping_phase9_variants.py`에 양방향 후보, 독립 절대 검증과 문서 전역 일대일 배정, 답 공개·비공개 Generator–Verifier, Mini→Pro 선별 경로를 작성했다. 합의만으로 직접 매핑을 결정하지 않고 각 원본에 별도 HOLD를 부여한다. 중복 대상이 우열을 가리기 어려우면 보류한다. 실제 모델별·업무별 경로 선택은 A 결과와 Risk 보정이 선행돼야 한다.
3. **추가 비교군.** SchemaTune의 도메인 검색기와 동적 reranking 분리, LLMatch의 스키마 준비·후보 선택·정렬 단계별 비교를 받아 후보 확장 효과와 포함된 후보의 판정 효과를 각각 잰다. 기존 로컬 후보를 고정한 소거를 먼저 하며, 추가 모델 학습의 효용은 검색 누락 열에서 개선 여지가 확인될 때 비교한다. 논문 벤치마크의 성능은 이 데이터에 그대로 적용하지 않는다. [SchemaTune EDBT 2026](https://www.openproceedings.org/2026/conf/edbt/paper-295.pdf) · [LLMatch](https://arxiv.org/abs/2507.10897)
4. **C.** Phase 7의 공식 DSPy transport, BootstrapFewShot·GEPA·MIPROv2와 paired 평가 예산 확보 방식을 재사용한다. 다음 구현에 RandomSearch, 업무 대조 증거를 넣은 MIPROv2와 Pro 교사 조건을 추가한다. 같은 Mini 입력과 블라인드 평가에서 전후를 비교하고 컴파일이 상한에 닿아도 평가 예산을 보존한다. 정확 추천·정상/과다 HOLD·업무 역할·자료형·중복·형식 오류를 개별 집계한다. [GEPA 논문과 코드](https://arxiv.org/abs/2507.19457) · [MIPRO 논문](https://arxiv.org/abs/2406.11695)
5. **D.** 로컬 고정밀+직접 HOLD 복원, Matchmaker+직접 판별, ConStruM+JevNexus, 양방향+독립 검증, GEPA+동적 예시, MIPROv2+대조 증거, 로컬+Mini+Pro 및 선정 조합을 비교한다. 구성 요소를 하나씩 빼고 정답 보존·복원·새 오추천과 호출·지연의 변화를 측정한다. Risk에서 공통·업무 영역·필드별 임곗값을 비교하고 정밀도 95%·98%·99%의 최대 정확 추천율을 기록한다. 표본이 부족한 그룹은 그룹별 보정 적용을 보류한다.
6. **E.** 확정 정책과 소스 지문이 고정된 뒤 새 Holdout을 한 번 평가한다. 문서군 단위 paired bootstrap과 정확 추천율·오추천·HOLD·계약·완전 매핑·필수 필드·사용자 수정 열·비용을 보고한다. 이 첫 평가에 맞춰 정책을 수정해야 한다면 별도 새 평가셋을 구성한다.

## 재현과 현재 상태

```powershell
$env:PYTHONPATH = 'backend;.;scripts;.artifacts/mapping-research/deps;.artifacts/mapping-research/metrics-deps'
$env:PERSISTENCE = 'disabled'
$env:OMP_NUM_THREADS = '2'
..venvScriptspython.exe scripts/evaluate_mapping_phase9.py plan
..venvScriptspython.exe -m pytest --no-db -q --tb=short
```

기본 출력은 Git 제외 경로 `.artifacts/mapping-research/phase9`의 데이터 매니페스트·동결 계획·로컬 결과다. A의 신규 Solar 실측은 요청 승인 대기, B의 새 조합은 오프라인 테스트 단계, C의 실제 최적화·D 소거·E 독립 결과는 미실행이다. Docker, PostgreSQL, 운영 기능과 승인 정책 변경은 없다. Phase 6의 기존 운영 검토 상태를 유지한다.

- 비DB 전체 pytest **1,359 passed, 68 skipped**. 9개 신규 테스트로 합성 분할, 저장 검증기의 월 표현, 전역 배정, 독립 검증, 선별 호출, 승인·예산과 원장 변경 시 차단을 확인했다.
- 최종 150개 본문의 지문과 전송 필드를 오프라인에서 다시 대조했다. Phase 3의 기존 Solar 응답 230문서를 캐시만으로 재생했고, 공식 DSPy·GEPA 런타임의 Phase 7 대역 비교 8개를 별도로 실행했다. 대역 결과는 실제 Solar 성능에 포함하지 않았다.
- 이번 단계 신규 API 요청·예약 0건. 기존 공용 원장 SHA-256 `868ab95fcb3f5f62d94110791b13a9641ec36d55db006d07451b751ed454e179`을 재확인했다.
