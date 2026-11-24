# 제조업 컬럼 매핑 · Phase 7 실제 LLM 추론과 호출 계획

2026-11-24 KST · Windows 보조 PC · 김대영 · 기준 [df06bf0](https://github.com/ChungPaMo/decision-supporter-mvp/commit/df06bf01c94738196abc11c649af663fbdeb8871)

## 논문에서 가져온 방식

| 비교 | 구현과 논문 대비 차이 |
| --- | --- |
| Matchmaker | 고정 HGB Top-3와 별도로 LLM이 전체 등록 필드에서 열당 후보 하나를 생성한다. 후보 합집합을 후속 LLM이 정제하고 별도 호출이 절대 적합성을 확인한다. 논문의 다중 벡터 검색과 무라벨 자기 개선 대신 기존 검색기와 고정 합성 학습 예시를 사용했다. [논문 §4·부록 C](https://arxiv.org/html/2410.24105) |
| JevNexus | 배치 요청의 후보별 독립 출력으로 MATCH·NON_MATCH·HOLD·TRANSFORM_REQUIRED를 받는다. 로컬 점수를 결합하고 원시 1위와 모순되거나 여럿이 비슷한 경우에 한해 다음 Listwise 호출을 한다. 수정은 첫 판정으로 지지되는 후보로 제한한다. 원 논문 모델의 로짓 결합은 적용하지 않았다. [논문 §3–4](https://arxiv.org/html/2610.09487v1) · [연구 코드](https://github.com/RazeenLI/JevNexus) |
| ConStruM | 동일 Top-3에 전체 업무 지식, 또는 적합성·혼동 역할 정의·주변 열·표 구조를 열당 420바이트에 제한한 대조 증거를 넣는다. 원 논문의 일반 하이퍼그래프 대신 고정 제조업 역할군과 원본 자료형·단위 및 행 관계를 사용했다. [논문 §4–5](https://arxiv.org/html/2601.20482v3) |
| Magneto 계열 | 동일 후보에서 Pointwise, 진짜 두 후보 비교, 동시 Listwise, 두 단계 및 순서 합의를 비교한다. 비교에서 이겨도 절대 적합성이 낮으면 승인 후보가 아니다. 순서 합의에는 원래 후보 순서와 역순을 썼다. [Magneto 구현](https://github.com/VIDA-NYU/magneto-matcher) · [순서 편향 연구](https://arxiv.org/abs/2608.03091) |
| 전체 스키마 | 단일 LLM 요청에서 전체 필드 비교, 업무 개념 ID로 판정 후 연결, 대상 필드별 원본 열 선택, Top-5 및 Generator–Verifier를 준비했다. 후자의 독립 판정은 원래 추천을 검증한다. 기존 추천 잠금과 HOLD 보완은 별도 경로다. |
| DSPy·GEPA | 공식 라이브러리 BootstrapFewShot, MIPROv2 및 GEPA를 사용했다. 모델 어댑터가 일반 판정, 예시 부트스트랩, 지시문 제안과 reflection을 하나의 유한 호출 경계를 통해 처리한다. 정책 컴파일은 Train과 Development에 한정했다. [DSPy 3.2.1](https://pypi.org/project/dspy/3.2.1/) · [GEPA](https://github.com/gepa-ai/gepa) · [MIPRO 논문](https://arxiv.org/abs/2406.11695) |

LLM 출력은 연구용 권고다. 스키마 enum·종료 상태·원본 열 ID·중복, 현 형식 제약과 잠긴 기존 추천을 확인한다. 의미적으로 맞더라도 백분율 형식처럼 정규화가 필요한 경우 직접 매핑에서 제외한다. 입력 근거에는 비율·통화·정수 관측 비율, 원본 샘플, 재고의 총량·할당·가용 관계, 수량과 금액·발주·반품의 역할 대조를 포함했다. 이 분석은 원본이나 등록·승인 경로를 변경하지 않는다.

Phase 6에서 BOM 손실 비율을 자재 소요량으로 분류한 18건과 금액·발주·반품을 안전재고로 분류한 4·4·1건을 재검토했다. 단위 없는 작은 소수가 투입량에도 나타날 수 있고, 정수 발주량과 반품량은 실제 재고와 자료형이 같다. 그래서 형식은 가능성을 좁히는 근거로 쓰고 업무 역할·관계가 지지하지 않으면 보류할 수 있도록 프롬프트와 독립 판정을 분리했다. [Phase 6 오류 분석](MAPPING_RESEARCH_PAPER_BENCHMARK_20261124.md#보류-복원과-실패-분석)

## 고정 데이터와 로컬 기준선

새 합성 홀드아웃은 5개 등록 엔터티, 20양식군, 60문서·464열이다. 직접 매핑 240열, HOLD 220열, 변환 필요 4열을 분리했다. Phase 6의 모든 분할과 정규화한 새 헤더가 겹치지 않는 것을 검사했다. 독립 회사 자료는 포함하지 않았다.

- Phase 7 독립 패널 SHA-256 `0e807fd926163e3e0f939b1c6f9036a1e6ac147e45b1d5bbc33292d7ac5ee1f9`
- Phase 6 정책 선택은 기존 동결 정책을 그대로 사용했다. 아래 첫 행의 검증은 이전 실험 재생이다. [Phase 6 보고서](MAPPING_RESEARCH_PAPER_BENCHMARK_20261124.md)

| 평가셋 | Exact/RapidFuzz 정답·오추천 | Phase 5 | Phase 6 |
| --- | ---: | ---: | ---: |
| 기존 Phase 6 회귀 200문서 | 211·3 | 341·68 | 510·27 |
| 신규 독립 60문서 | 15·6 | 53·5 | 61·11 |

신규 60문서의 Phase 6 정확 추천율은 25.42%, 정밀도는 84.72%, 전체 오추천율은 2.37%, HOLD 정답 거절률은 97.32%였다. 원시 Top-3는 220/240, 최종 Top-3는 64/240, 완전 매핑은 3/60이었다. 데이터 생성은 BOM의 소요량과 손실률이 모두 1보다 작은 수를 갖도록 설계했다. 값의 크기만으로 역할을 구분할 수 없다. 금액·발주·반품은 수량처럼 보이는 값도 포함했다.

## 실제 Qwen 추론

기존 Qwen2.5-1.5B Instruct GGUF를 llama.cpp의 루프백 CPU 서버에서 사용했다. 가중치 SHA-256은 `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`다. 네트워크 비용은 0이다. Selection의 BOM·재고 고정 2문서에는 22열 중 18개 직접 매핑 정답이 있다. Exact/RapidFuzz 18·0, Phase 5 15·0, Phase 6 16·0이었다.

| Qwen 방식 | 정답 / 18 | 오추천 / 22 | 계약 영향 / 2 | 실제 요청 | 문서 P50/P95(초) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 기존 프롬프트 직접 매핑 | 4 | 4 | 1 | 2 | 9.50 / 13.42 |
| 업무 정의를 추가한 전체 스키마 | 0 | 1 | 2 | 2 | 14.89 / 20.81 |
| Matchmaker | 16 | 1 | 1 | 6 | 30.98 / 40.44 |
| JevNexus 선택적 공동 비교 | 15 | 0 | 2 | 4 | 27.86 / 39.44 |
| ConStruM 전체 지식 | 14 | 1 | 2 | 2 | 11.88 / 15.62 |
| ConStruM 동적 증거 | 14 | 1 | 2 | 2 | 23.04 / 29.38 |
| Magneto Pointwise | 16 | 0 | 1 | 2 | 28.73 / 38.98 |
| Magneto Pairwise | 0 | 0 | 0 | 2 | 29.06 / 39.62 |
| Magneto Listwise | 14 | 1 | 2 | 2 | 11.31 / 15.42 |
| Pointwise + Listwise | 14 | 1 | 2 | 4 | 26.62 / 34.50 |
| 후보 순서 합의 | 3 | 3 | 0 | 4 | 20.85 / 27.95 |
| Top-5 Listwise | 15 | 2 | 1 | 2 | 15.85 / 19.07 |
| Generator–Verifier | 0 | 2 | 2 | 4 | 41.19 / 62.46 |

계약 영향은 문서에 중복 대상이나 구조 위반이 한 건이라도 있었음을 뜻한다. 중복 중 일부를 차단한 열의 평가지표와 문서 단위 계약 영향은 다른 지표다. CPU 타이밍은 작은 표본의 관측치이며 일부 구간에는 다른 로컬 검증 작업이 함께 실행됐다.

같은 후보를 받은 전체 지식과 동적 증거의 채점은 같았다. Top-5는 Listwise에 정답 1개와 오추천 1개를 더했다. Pointwise에 Listwise를 추가하면 정답이 2건 감소하고 오추천 1건이 늘었다. Matchmaker·JevNexus·Pointwise 모두 원시 후보를 벗어난 추가 정답을 이 Selection 표본에서는 보여주지 못했다. 원시 Top-3에 이미 18개 정답이 모두 있었다. Top-3 밖 후보의 채택은 테스트 대역으로 확인했다.

모든 요구 지표를 만족한 선택 정책이 없었다. 후속 탐색에는 정답이 있는 후보 중 오추천이 가장 적고 다음으로 정답이 가장 많은 Pointwise를 동결했다. Selection 정책 SHA-256은 `7654b5aa9dda560253a34cf14e17b4c793fa2cabc17cdfc5606aabef9871076e`다. 모든 열을 HOLD한 Pairwise는 선택에서 제외했다.

### 새 양식군 검증

신규 60문서 중 사전에 고정한 5개 엔터티의 양식군별 한 문서와 백분율 BOM 한 문서, 총 **6문서·46열·27개 직접 매핑 정답**에 실제 Qwen 두 방식을 비교했다. 나머지 54문서는 위 로컬 기준선 평가에만 포함했다.

| 동일 6문서 | 정답 | 오추천 | 정확 추천율 | 정밀도 | HOLD 정답 거절률 | 계약 영향 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Exact/RapidFuzz | 0 | 0 | 0% | 해당 없음 | 100% | 해당 없음 |
| Phase 5 | 5 | 1 | 18.52% | 83.33% | 100% | 해당 없음 |
| Phase 6 | 5 | 2 | 18.52% | 71.43% | 100% | 해당 없음 |
| Qwen 기존 직접 매핑 | 4 | 11 | 14.81% | 26.67% | 78.95% | 4/6 |
| Qwen Pointwise 고정 | 3 | 3 | 11.11% | 50.00% | 94.74% | 2/6 |

Pointwise의 전체 오추천율은 6.52%였다. Phase 6 대비 새 정답 2건과 새 오추천 1건이 있었고 기존 정답 4건을 잃었다. Pointwise의 원시 Top-3에는 22/27 정답이 있었지만 최종 Top-3에는 3/27만 남았다. 어떤 방식도 완전 매핑 문서를 만들지 못했다. Pointwise는 백분율을 직접 등록하지 않았으며 해당 역할의 변환 필요 상태도 식별하지 못했다.

Pointwise의 세 오류는 신규 발주 대기 수량을 `safety_stock_qty`로, 제품 코드인 `Released item registry code`를 `product_name`으로, 기준 산출량 `Nominal lot yield`를 `line_no`로 판정한 사례였다. 전체 60문서의 Phase 6 기준선에서도 반품 6열을 안전재고로 추천했다. 발주·반품에는 값의 크기보다 주문 이벤트와 재고 정책의 관계를 지지하는 근거가 필요하다. 단순히 후보 설명이나 문맥을 추가하는 것만으로 이 오류가 해결되지는 않았다.

6회 요청에서 직접 매핑은 입력·출력 4,411·249토큰과 문서 P50/P95 6.65/10.51초, Pointwise는 4,228·1,148토큰과 16.29/24.10초를 사용했다. 실제 Qwen 비교는 모든 배포 목표에 미달했다. 현재 운영 후보는 원본 검증을 유지하는 기존 경로다. 후속 Solar 검증은 기존 정상 추천을 잠근 채 HOLD에서 얻는 순이득과 새로운 오추천을 먼저 측정한다.

## 공식 옵티마이저 실행

DSPy 3.2.1·GEPA 0.0.27·Optuna 4.9.0을 독립 경로에 설치했다. Train·Development 각 2개의 합성 문서로 컴파일하고 Selection의 역할 혼동 양식 2개로 전후를 비교했다. 샘플은 소요량·손실률·재고 역할과 오프스키마 열을 추린 자료다. 표의 점수는 형식·중복·역할·오추천·과다 HOLD에 서로 다른 가중치를 적용한 0~1 연구 점수다.

| Qwen 옵티마이저 실측 | 전→후 | 관측 |
| --- | ---: | --- |
| 기존 프롬프트 | 0.000→0.000 | 두 평가의 형식 실패 |
| 수동 프롬프트 | 0.045→0.000 | 최종 형식 실패 |
| Dynamic Few-shot | 0.167→0.000 | 최종 형식 실패 |
| BootstrapFewShot | 0.045→0.343 | 응답이 구조화됐으나 새 오추천·과다 HOLD·업무 역할 오류가 각각 1건 |
| MIPROv2 | 0.045→0.045 | 의미 있는 개선을 확인하지 못함 |
| GEPA | 미확정 | 실제 26회, 탐색 중 호출 상한 도달. 쌍별 전후 결과를 확정할 수 없음 |
| GEPA + Dynamic Few-shot | 미확정 | 실제 26회, 호출 상한 도달 |
| GEPA + Generator–Verifier | 0.045→0.250 | 실제 24회, 컴파일 상한 도달. 형식 오류와 HOLD가 남았고 독립 Verifier 실호출에 넘길 유효 후보가 없었음 |

GEPA 두 방식의 최초 실행에서는 탐색 중 예산 소진이 형식 실패로도 집계됐다. 이를 정확도 개선 근거에서 제외했다. 검토용 코드에는 컴파일과 전후 평가의 호출 예산을 분리했고 소진 상태를 기록하도록 수정했다. 공식 대역 8개 비교에서 이 흐름과 독립 Verifier 호출을 확인했다. 대역 점수는 정확도 비교에 포함하지 않는다.

## 비용 경계와 Solar 실행 계획

새 공급사 사용량 CSV를 발견하지 못했다. 공용 원장의 기존 계산 USD 2.02422308과 미확정 예약 USD 7.88260000, 합계 **USD 9.90682308**을 유지했다. 잔액은 USD 0.09317692다.

| 단계 | 최대 요청 | 최대 입력 토큰 대용치 | 최대 출력 토큰 | 예약 추정 상한(USD) |
| --- | ---: | ---: | ---: | ---: |
| 합성 BOM·재고 2문서 × 5방식 × 3모델 | 30 | 286,764 | 9,600 | 0.05960900 |
| 20문서 × 일반 20방식 × 3모델 | 1,920 | 41,303,040 | 1,966,080 | 9.01401600 |
| 7가지 최적화 비교, Mini 단독 | 108 | 2,323,296 | 27,648 | 0.26772768 |
| 7가지 최적화 비교, 세 모델 | 324 | 6,969,888 | 82,944 | 1.33863840 |

작은 비교의 입력 대용치는 정확한 30개 요청 본문 바이트에 건당 512를 더해 구했다. 넓은 비교의 상한은 건당 21,000바이트를 기준으로 계산했다. 정산 전 추정치이며 10% VAT와 Preview 할인 전 가격을 적용했다. Mini 4 및 Mini 4.5 Preview는 입력/출력 백만 토큰당 USD 0.10/0.40, Pro 4는 USD 0.30/1.20이다. 4.5 Preview는 공식 문서상 2026-11-30 종료 예정이다. [Upstage 가격](https://www.upstage.ai/pricing/api) · [Mini 4.5 Preview](https://console.upstage.ai/docs/models/solar-mini-4-5-preview) · [Chat API](https://console.upstage.ai/api/chat)

2문서 실험은 기존 Phase 6 Development에서 파일 해시로 고정한 BOM·재고 각 1문서만 전송한다. 입력은 합성 제목·헤더·열당 값 최대 3개, 표준 스키마와 업무 정의, 파생 프로파일과 로컬 후보 순서다. 정답·학습 예시·신규 독립 패널 원본은 이 범위에 포함하지 않는다. 독립 평가에 대한 별도 전송 승인도 필요하다. 실행 파일은 동일 계획 SHA, 현재 원장 잔액, 별도 승인 금액을 함께 확인하고 공용 캐시·락·비용 예약을 사용한다.

초기 스모크는 고정 30개 본문의 SHA까지 대조한다. 2문서로 20방식까지 확장한 명시 승인 계획은 최대 192회, USD 0.90140160으로 현재 잔액을 초과한다. Matchmaker의 합성 학습 예시와 공식 DSPy의 교사·reflection 입력을 외부로 보내려면 승인 범위에 각각 포함해야 한다. 이 단계는 기존 예약의 공급사 증빙 대조 또는 추가 비용 승인이 필요하다.

초기 계획 SHA-256은 `733aecadca9f04e51b4a4466b1239f1062417a561e89ba1ee448d3a555287555`다. 합성 입력 전송과 실험비 배정 승인이 접수되기 전이므로 **신규 Solar 호출 0건**이다. Mini·Pro·Preview의 직접 매핑과 논문 방식, Solar 기반 최적화, 합성 독립 패널의 유료 측정과 Risk 분할의 Solar 보정은 모두 **NOT_RUN**이다. 기존 Phase 3 Solar 230문서의 캐시 재생은 통과했고, 공용 원장 SHA가 유지됐다. 이 캐시로 새 프롬프트 성능을 추정하지 않았다.

## 재현

```powershell
$env:PYTHONPATH='backend;.;scripts;.artifacts/mapping-research/deps;.artifacts/mapping-research/metrics-deps'
$env:PERSISTENCE='disabled'
$env:OMP_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='2'
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase7.py plan
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase7.py plan --recipe-set full
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase7.py baselines
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase7.py local-development
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase7.py freeze-local
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase7.py local-holdout
.\.venv\Scripts\python.exe -m pytest --no-db -q --tb=short
$researchDeps='.artifacts/mapping-research/phase7/optimizer-deps'
.\.venv\Scripts\python.exe -m pip install --target $researchDeps dspy==3.2.1 gepa==0.0.27 optuna==4.9.0
$env:PYTHONPATH += ";$researchDeps"
.\.venv\Scripts\python.exe scripts/mapping_phase7_optimizer.py --mock
.\.venv\Scripts\python.exe scripts/mapping_phase7_optimizer.py --local --threads 2
```

결과는 Git 제외 경로 `.artifacts/mapping-research/phase7`에 저장한다. `solar-development`는 별도 승인에 연결한 계획 SHA와 최대 USD 및 학습 예시 승인 여부를 요구한다. 실행 전 새 모델 버전·요금과 공용 원장을 확인한다.

Windows Python 3.11에서 비DB pytest **1,350 통과·68 건너뜀**, 기존 Starlette 경고 1건을 확인했다. RapidFuzz 48건·70건의 Top-3는 각각 26/32·6/37로 재현했다. OpenAPI·JSON Schema 일치와 변경 파일 보안 검사 발견 0건을 확인했다. PostgreSQL·Docker 작업은 미실행이다.
