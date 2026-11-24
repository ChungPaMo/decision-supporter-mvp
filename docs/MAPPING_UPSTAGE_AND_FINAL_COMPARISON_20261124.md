# 제조업 컬럼 매핑 Phase 2 · Upstage 실측과 로컬 독립 검증

2026-11-24 KST · 기준 `main` [`61cf597`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/61cf597608839b1f8754f7ccbf9266f43b9a4c44) · [Phase 1](MAPPING_COMPREHENSIVE_RESEARCH_20261124.md) · [문서 분석 실측](MAPPING_UPSTAGE_DOCUMENT_INTELLIGENCE_20261124.md)

## 요약

**운영은 기존 정확 일치·사용자 검토 흐름을 유지하는 편이 근거가 강하다.** 표준 별칭이 섞인 신규 100문서에서 정확 일치는 280열을 오추천 없이 찾았다. Phase 1의 가장 강한 LightGBM은 같은 셋에서 정확 71열·오추천 25열이었다. 로컬 비표준 어휘 연구와 실제 양식에서 같은 모델 순위가 나올 것이라고 볼 수 없다.

소규모 최종 표 5개·47열에서 Solar Pro 전체표는 정답 20, 오추천 1, 정밀도 95.24%였다. Mini 단독 8·2, Mini+업무 지식 20·2, 같은 5개에서 LightGBM 14·1이었다. Mini를 LightGBM HOLD에만 적용하면 정답 2개와 오추천 1개가 함께 늘었다. 범위, 사용량 및 구조화 응답 실패를 고려하면 Solar는 낯선 표의 후보 검토용 실험이다. 실기업 입력의 외부 처리와 운영 도입은 별도 검증 대상이다.

## 실행 환경과 고정 데이터

- Windows 10 보조 PC, Python 3.11.9, Ryzen 5 5600G 6코어·12스레드, 작업 시작 가용 RAM 5,148 MiB. CPU 모델을 순차 실행했다. SaaS 호출은 로컬 모델 RAM 측정에 포함하지 않았다.
- Phase 1의 Train 975문서·8,539열, Calibration 80문서·703열, Final 130문서·1,132열과 SHA를 보존했다. 새 임계값은 Calibration만 사용했다. 전체 최종의 결과는 로컬 모델에서만 확인했다. Upstage Final은 제안 스키마별 첫 문서로 고정한 5문서·47열이며 그중 직접 매핑 23열과 HOLD 24열이다. 잘못된 제안 스키마의 문서도 포함했다. 5문서 보정 스모크는 36열·직접 매핑 26개다.
- 독립 Confirmatory는 원본 템플릿 생성기와 다른 날짜·반복 코드·수량 분포·별칭·업무 표현으로 만든 100문서·980열, 25개 양식군이다. 정답 645열, HOLD 335열. 표준 토큰·띄어쓰기 별칭 및 비표준 현장 표현이 섞이고 필수 열 누락과 잘못 분류된 문서가 포함됐다. 해시 `ea4a86ed84dcfd12400f46cd11ea87d3f6a266a89040299e611752ea7eba5649`를 실행 전에 기록했다. 학습·보정과 CSV SHA 교차 중복은 0이었다. 검증은 평면 표의 열 매핑이며 복합 XLSX 구조는 별도 보고서에서 다룬다.
- API 입력은 사전 고정한 합성 데이터의 헤더, 제목, 값 샘플, 자료형·프로파일과 대상 계약만 받는다. 평가용 정답·생성 역할·정답 문서 종류는 보낸 요청에 없다. Confirmatory는 로컬 전용이다.

## 공식 모델과 스모크

| 모델 | 사용 ID | 컨텍스트·제한 | 정가 USD / 1M 토큰, 세전 |
| --- | --- | --- | --- |
| Solar Mini 4 | `solar-mini4-260922` | 512K 컨텍스트, 최대 128K 출력. 공개 기본 100 RPM / 250K TPM | 입력 0.10 / 출력 0.40 / 캐시 입력 0.01 |
| Solar Pro 4 | `solar-pro4-260806` | 512K 컨텍스트, 최대 128K 출력. 공개 기본 100 RPM / 250K TPM | 입력 0.30 / 출력 1.20 / 캐시 입력 0.03 |
| Embedding 2 | `solar-embedding-2-query` / `solar-embedding-2-passage` | 1,024차원, 입력 8K, 요청 배열 최대 100개, ID별 100 RPM / 300K TPM | 0.02 |

실험은 `reasoning_effort=none`, `temperature=0`, `strict` JSON Schema, 128+40×요청 열 수 최대 출력, 보수적인 리스트 가격을 사용했다. Mini 프로모션 단가와 공급사 입력 캐시 할인은 원장에 적용하지 않았다. 응답의 ID 누락·중복, 허용 대상 밖 필드와 반복된 대상 필드를 계약 실패로 처리했다. 보정 스모크는 Mini 4/5, Pro 5/5가 계약을 통과했다. Embedding 응답에서 정규화할 수 있는 1,024차원 유효 벡터와 대응 인덱스를 확인했다. [Chat API](https://console.upstage.ai/api/chat) · [Snapshot과 요청 제한](https://console.upstage.ai/ko/docs/capabilities/generate/chat) · [Mini](https://console.upstage.ai/docs/models/solar-mini-4) · [Pro](https://console.upstage.ai/docs/models/solar-pro-4) · [Embedding](https://console.upstage.ai/docs/capabilities/embed) · [가격](https://www.upstage.ai/pricing/api)

Mini 4.5 Preview는 공식 Responses API의 별도 미리보기이며 호출하지 않았다. Solar Pro 2·3의 공식 종료일은 2026-10-30 KST, Embedding 1 종료 예정일은 2026-12-31 UTC다. 표준 모드의 공식 안내는 입력을 모델 학습에 쓰지 않으며 서비스 제공에 필요하다고 명시된 범위에서만 보관한다고 설명한다. 데이터 공유 조건이 다른 Contributor 모드는 사용하지 않았다. [Preview](https://console.upstage.ai/docs/models/solar-mini-4-5-preview) · [서비스 일정과 가격](https://www.upstage.ai/pricing/api) · [Contributor 조건](https://console.upstage.ai/docs/guides/contributor-mode)

## Solar 실측과 구조 비교

| 같은 5문서·47열 / 정답 23개 | 정확 Top-1 | 최종 Top-3 | 오추천 | HOLD | 정밀도 | HOLD 거절 | 전체 열 일치 문서 | 계약 실패 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Phase 1 LightGBM | 14 | 14 | 1 | 32 | 93.33% | 23/24 | 0/5 | — |
| Solar Mini 전체표 | 8 | 8 | 2 | 37 | 80.00% | 22/24 | 1/5 | 2/5 |
| Solar Pro 전체표 | 20 | 20 | 1 | 26 | 95.24% | 23/24 | 2/5 | 1/5 |
| Solar Mini 전체표 + 업무 지식 | 20 | 20 | 2 | 25 | 90.91% | 22/24 | 1/5 | 1/5 |
| LightGBM HOLD만 Mini 문서별 재검토 | 16 | 16 | 2 | 29 | 88.89% | 22/24 | 0/5 | 4/5 |
| Solar Embedding 2 전체 문맥 | 1 | 1 | 0 | 46 | 100%, 추천 1건 | 24/24 | 1/5 | 0 |

Solar 단독은 한 후보 또는 HOLD를 반환해 독립 Top-3 순위를 만들지 않는다. 표의 Top-3는 단일 후보를 집계한 값이다. 구조화 응답이 실패한 문서의 열은 HOLD로 채점했다. `문서 전체 열 일치`는 모든 정답과 HOLD가 일치한 문서다. LightGBM HOLD 방식은 이미 추천한 열 15개를 그대로 두고 32개 HOLD만 다시 검토했다. 기존 정답 14/14가 유지됐다. Mini 전체표와 같은 5회 요청이므로 호출 수 절감은 0이다. 컬럼별 32회와의 요청 수 차이는 설계상 비교이며 해당 컬럼별 HOLD 방식은 실제 실행하지 않았다.

컬럼 단독은 위 5문서의 첫 열만 따로 요청했다. 직접 매핑 정답 4개에서 Mini는 1개 정답, 오추천 1건, HOLD 3개였고 Pro는 4개 정답과 오추천 1건이었다. Embedding 전체 문맥 Top-3 제한 + Mini는 같은 5열에서 4개 정답과 오추천 1건이었다. 이 결과는 보조 후보 검색이 유효할 수 있다는 작은 관찰이며 Fold 단위 일반화 근거는 아니다. 전체표가 컬럼 단독보다 유리한지 판단할 수 있는 모든 열의 쌍대 실험은 미실행이다. Embedding 단독 원시 Top-1/3/5는 13/17/21, HOLD 이후 정확 1개였으므로 높은 후보 회수와 운영 적합성은 별개다.

| Phase 2 실행 상태 | 실측 범위 또는 사유 |
| --- | --- |
| A1–A4 Mini·Pro 컬럼/전체표 | 컬럼 단독 5열, 전체표 5문서. 각 모델 고정 패널 |
| A5 Mini 업무 지식 | 같은 5문서 실측. Pro 업무 지식 A6 `NOT_RUN` |
| B1–B5 Embedding | B3 전체 문맥만 보정·최종 각 5문서 실측. 다른 문맥 조건 실행기는 준비했으며 `NOT_RUN` |
| C1–C6 LightGBM+Solar | C3/C5 Mini HOLD만 문서별 묶음 실측. Pro HOLD, 전열 후보 검증, 불확실 추천 재검토 `NOT_RUN` |
| D/E 추가 하이브리드 및 개념 판별 | Embedding+Mini 후보 제한 5열 실측. RapidFuzz·BGE·Qwen 후보와 Solar 결합, 개념 분류 또는 두 단계 검토 `NOT_RUN` |
| 전체 130문서 유료 평가 | 자동 승인 검토가 외부 전송 범위 확장을 이유로 거절. 단일 Mini 방식도 SHA·130회·0.12 USD 상한을 사전 명시한 요청이 거절돼 `NOT_RUN` |

## 로컬 모델, 전용 Reranker와 학습

| 동일 1,132열 기준 | 원시 Top-1 / 3 / 5 | 정확 Top-1 | 최종 Top-3 | 오추천 | HOLD |
| --- | ---: | ---: | ---: | ---: | ---: |
| BGE-M3 Q4 ONNX 헤더 | 558 / 755 / 778 | 205 | 228 | 59 | 868 |
| BGE-M3 Q4 ONNX 전체 문맥 | 310 / 592 / 729 | 15 | 15 | 2 | 1,115 |
| Qwen3-Embedding-0.6B Q8_0 헤더 | 536 / 714 / 754 | 164 | 189 | 28 | 940 |
| Qwen3-Embedding-0.6B Q8_0 전체 문맥 | 472 / 673 / 730 | 27 | 27 | 0 | 1,105 |
| E5 동일 헤더, 원본 → LayerNorm 학습 | 359 / 577 / 714 → 353 / 576 / 714 | 12 → 12 | 12 → 12 | 0 → 0 | 1,120 → 1,120 |

BGE·Qwen은 Phase 1 캐시를 재사용했다. 전체 문맥의 신규 최종 실행을 완료했으며 보정이 더 많은 열을 거절했다. BGE Q4 전체 문맥 평균 배치 단위 1고유열 P50/P95 175/510 ms, Qwen Q8은 392/670 ms였다. BGE Python 최대 RSS 2,560 MiB. Qwen Python 최대 126 MiB는 llama.cpp 자식 프로세스를 제외한다. 재개 시간 BGE 약 156초, Qwen 약 382초는 초기화와 캐시 확인을 포함하며 과거 캐시 추론은 제외한다.

**실제 가중치 학습.** 기존 E5 ONNX의 12번째 인코더 레이어 출력 LayerNorm `weight`와 `bias` 총 **768/117,505,920개**(~0.00065%)를 직접 학습했다. 200문서·1,814열에서 양성 필드와 HOLD를 포함한 다중 대조 손실을 1.95379→1.94451로 낮췄다. 학습 0.79초, 모델 복제·스코어링을 합쳐 10.64초, 최대 2,272 MiB. 학습 전후 ONNX SHA가 다르며 재로딩한 실제 출력과 계산값의 최대 오차는 `2.43e-8`이었다. 성능은 그대로이고 원시 Top-3는 1개 감소했다. LoRA, Triplet, 전체 인코더 학습은 미실행이다.

전용 Reranker는 원래 분리에서 제안 스키마별 1문서의 첫 4열씩 보정·최종 각 20열을 고정했다. 최종 정답 대상은 14열이다.

| Reranker 구성 | 원시 Top-3 | 정확 Top-1 / 최종 Top-3 | 오추천 | HOLD |
| --- | ---: | ---: | ---: | ---: |
| mMiniLM 모든 쌍 | 12 | 1 / 1 | 0 | 19 |
| BGE v2-M3 INT8 모든 쌍 | 13 | 4 / 5 | 1 | 15 |
| BGE 검색 Top-3 + BGE Reranker | 11 | 4 / 5 | 1 | 15 |
| LightGBM Top-3 + BGE Reranker | 12 | 4 / 5 | 1 | 15 |
| Qwen3-0.6B Q4_K_M 모든 쌍 | 9 | 5 / 6 | 1 | 14 |
| Qwen 검색 Top-3 + Qwen Reranker | 12 | 5 / 6 | 1 | 14 |
| LightGBM Top-3 + Qwen Reranker | 12 | 5 / 6 | 1 | 14 |

BGE INT8 리비전 `6f5ff65298512715a1e669753bc754d2bc8f367b`, Qwen Q4_K_M `7af0c7c371b5ad3daf771ce4f6d091a4d38c799a`다. 열당 모든 쌍 CPU P50/P95는 BGE 0.93/2.29초, Qwen 3.15/6.26초다. BGE Python 최대 RSS 1,164 MiB였다. Qwen은 별도 llama.cpp 프로세스 메모리가 필요하다. 정확도 비교는 같은 전체 점수에 후보 마스크를 적용했으며, 후보 제한 추론 시간은 따로 측정하지 않았다. [Qwen 원본](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) · [Q4 변환](https://huggingface.co/gorse-io/Qwen3-Reranker-0.6B-GGUF) · [BGE ONNX 변환](https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX)

로컬 llama.cpp `b12657`에서 스키마 직접 전달, 배열 개수 고정, thinking 차단, 컨텍스트 4,096과 늘린 출력 한도를 같이 적용했다. Qwen3-0.6B Q8_0과 Qwen2.5-1.5B Instruct Q4_K_M은 첫 열 5개 모두 계약을 충족했고 두 모델 모두 3정답·2오추천이다. 전체표는 두 모델 각각 5개가 모두 계약 실패였다. 열 단독 P50/P95는 2.77/3.90초와 3.12/4.96초, 전체표는 8.22/27.11초와 16.00/30.45초였다. 원래 Phase 1의 JSON 실패가 단순 모델 크기의 문제였다고 결론낼 수 없다. 종료 상태·길이·구조화 계약·의미 정확도를 나눠 기록했다. [llama.cpp 서버 계약](https://github.com/ggml-org/llama.cpp/blob/b12657/tools/server/README.md) · [Qwen2.5 GGUF](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF)

## 독립 로컬 성능과 운영 판단

| Confirmatory 100문서, 980열 / 정답 645 | 정확 | 최종 Top-3 | 오추천 | HOLD | 정밀도 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 정확 일치 | 280 | 280 | 0 | 700 | 100% |
| RapidFuzz | 278 | 278 | 0 | 702 | 100% |
| Phase 1 LightGBM | 71 | 73 | 25 | 884 | 73.96% |
| LightGBM Ranker | 114 | 136 | 94 | 772 | 54.81% |
| 공통 형식 가드를 적용한 Exact → LightGBM | 244 | 246 | 12 | 724 | 95.31% |
| 공통 형식 가드를 적용한 RapidFuzz → LightGBM | 250 | 252 | 12 | 718 | 95.42% |

Confirmatory는 Phase 1의 평면 문서와 값 분포가 다르다. Ranker는 학습용 양성 그룹에서 순위를 학습하고 Calibration에서 HOLD를 고정했으나 오추천이 늘었다. 별칭 우선 두 조합은 공통 가드가 기존 후보도 검사했으며 단순 별칭보다 정답·오추천 양쪽에서 열세였다. 별도의 업무 개념 분류기, 필드별 문턱과 hard-negative 전용 학습은 후속 범위다.

- **정확**. 같은 원격 5문서에서 Pro 전체표와 Mini+업무 지식은 각각 20개 정답이었다. Pro 오추천 1건, Mini 2건이다. 별칭이 섞인 독립 셋에서 정확 일치가 가장 많은 정답과 가장 적은 오추천을 동시에 기록했다. 모든 모델을 독립 기업 데이터에 비교한 결과는 없다.
- **속도·비용**. 독립 표에서 문서당 정확 일치 P50 0.073 ms, RapidFuzz 0.91 ms, LightGBM은 특징 계산을 포함해 5.87 ms였다. 입력 읽기와 API 호출을 포함하지 않은 로컬 단계 시간이다. Mini는 소규모 API에서 빠르고 저렴했고, 업무 가이드 추가로 정답이 8→20개 늘었다. 소규모 성능으로 Mini/Pro의 실제 기업 비용 효율을 순위화할 근거는 부족하다. 외부 장애 시 기존 파서·정확 일치·사용자 검토로 계속 처리할 수 있다.
- **MVP**. 정상 XLSX는 범위와 원본 셀을 확인하고 기존 정확·별칭 후보를 제시한다. 불확실한 열은 HOLD와 수동 비교를 유지한다. LightGBM과 Solar는 신규 양식에서 후보를 비교하는 shadow 대상으로 두고, 공식값·필수 매핑·명시적 승인 경로를 유지한다. 기업 문서 외부 전송 승인이나 운영 교체는 이번 연구 범위에 포함되지 않았다.

## 공용 비용 원장

`billing.jsonl`에 Solar, Embedding, Parse, Classify, Extract의 동일 전역 잠금과 예약액을 적용했다. 요청 실패는 예약을 보존하고 같은 요청을 자동 재전송하지 않았다. 성공 캐시는 모델·입력·설정과 응답 SHA를 확인한다. 키는 Git 무시를 확인한 로컬 파일에서 지정 변수 한 개만 읽었고, API 호출 원장에는 요청 해시·모델·사용량·비용·시간만 남겼다. 사용량 가격 계산과 공급사 계정 청구는 별개다.

최종 **HTTP 94회**, 응답 수신 92회, HTTP 400 2회다. 정가·VAT를 적용한 사용량 비용 **1.01965941 USD**, 실패 예약 **0.11000000 USD**, 합계 **1.12965941 USD**이며 승인 한도 잔여 **3.87034059 USD**다. 스키마 검증에 실패한 HTTP 성공 응답의 비용도 포함한다.

| 텍스트 모델 | 요청 / 수신 | 입력 토큰 | 출력 토큰 | 계산 비용 USD VAT 포함 |
| --- | ---: | ---: | ---: | ---: |
| Solar Mini 4 | 35 / 35 | 37,283 | 2,776 | 0.005323 |
| Solar Pro 4 | 15 / 15 | 15,088 | 1,176 | 0.006531 |
| Embedding 2 query | 2 / 2 | 8,596 | — | 0.000189 |
| Embedding 2 passage | 1 / 1 | 744 | — | 0.000016 |
| Document Classify | 12 / 12 | 28,236 | 751 | 0.061600 |
| Information Extract Standard | 6 / 5 | 26,356 | 3,655 | 0.220000 + 0.044000 실패 예약 |
| Information Extract Enhanced | 6 / 5 | 29,937 | 3,684 | 0.330000 + 0.066000 실패 예약 |

Parse는 응답에 페이지·모드가 있으며 토큰 보고가 없다. 원장의 페이지·모드별 계산과 지연은 [Document Intelligence 보고서](MAPPING_UPSTAGE_DOCUMENT_INTELLIGENCE_20261124.md#공용-예산과-속도)에 기록했다. Mini 호출 P50 약 0.76초, Pro 약 1.65초, Embedding query 약 0.26초다. 이 지연에는 여러 채팅 방식의 응답을 포함한다.

## 재현 및 검증

추가 의존성은 기존 `.venv`에 혼합하지 않고 아래 Git 제외 경로에 설치한다. 모든 모델과 원시 응답은 `.artifacts/mapping-research/` 아래에 있다. CPU 재실행에서 기존 neural 캐시를 활용한다.

```powershell
$base = '.artifacts/mapping-research'
$out = "$base/phase2"
$llama = "$base/models/llama/llama-server.exe"
New-Item -ItemType Directory -Force "$base/deps" | Out-Null
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: --target "$base/deps" -r scripts/mapping_research_requirements.txt
$env:PYTHONPATH = "scripts;$base/deps"
.\.venv\Scripts\python.exe scripts/mapping_research_confirmatory.py prepare
.\.venv\Scripts\python.exe scripts/mapping_research_confirmatory.py evaluate
.\.venv\Scripts\python.exe scripts/mapping_research_phase2.py chat --plan --mode table --model mini --per-entity 1 --output "$out/final-panel-mini-table.json"
.\.venv\Scripts\python.exe scripts/mapping_research_remote.py audit --output "$out/billing-summary.json"
.\.venv\Scripts\python.exe scripts/mapping_research_e5_tune.py --model "$base/models/e5"
.\.venv\Scripts\python.exe scripts/mapping_research_neural.py bge-q4 --model "$base/models/bge-q4" --threads 4 --batch 4 --modes header full
.\.venv\Scripts\python.exe scripts/mapping_research_neural.py qwen --model "$base/models/qwen-embedding.gguf" --llama $llama --threads 4 --batch 16 --modes header full
.\.venv\Scripts\python.exe scripts/mapping_research_local_phase2.py bge-reranker --model "$base/models/bge-reranker" --output "$out/bge-reranker-pilot.json"
.\.venv\Scripts\python.exe scripts/mapping_research_local_phase2.py qwen-reranker --model "$base/models/qwen-reranker/model.gguf" --llama $llama --output "$out/qwen-reranker-pilot.json"
.\.venv\Scripts\python.exe -m pytest --no-db -q --tb=short
```

생성 결과와 캐시를 다시 사용하는 경우 Phase 1의 재현 절차에서 원래 입력·점수·공개 모델을 복원한다. 소규모 Upstage 실측은 `chat --mode table`(또는 `business`, `hold`) `--model mini|pro --per-entity 1 --approved-paid-api --output ...`로 동일 고정 패널을 선택한다. 컬럼 방식은 `--mode column --columns-per-doc 1`, Embedding은 `embed --mode full --per-entity 1`이다. 직접 호출은 연구 승인 범위에서만 사용하고 누적 원장·캐시를 보존한다. 생성한 Confirmatory, 파생 PDF와 원시 응답은 Git 제외 경로에 둔다.

보조 PC에서 전체 비DB pytest **1,259 통과 · 68 건너뜀**, 연구 회귀 20 통과를 확인했다. 기존 48건은 Top-1 25/32, Top-3 26/32, 오추천 3/48이고 70건은 5/37, 6/37, 7/70으로 재현됐다. 기존 OpenAPI·JSON Schema 동기화 검사도 전체 테스트에 포함됐다. 변경 14개 파일의 보안 탐지와 실제 로컬 키 일치 문자열은 각각 0건이다. 운영 앱·계약·팀 모듈과 DB 변경은 없다.
