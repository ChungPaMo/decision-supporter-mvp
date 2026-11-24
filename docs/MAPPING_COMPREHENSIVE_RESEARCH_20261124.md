# 제조업 컬럼 매핑 종합 벤치마크

2026-11-24 KST · 기준 `main` [`560de30`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/560de30b20fb365e5e9e12aa229eac53c0dc912b) · [선행 연구와 공개 구현](MAPPING_RESEARCH_LITERATURE_20261124.md)

## 요약

가장 유망한 로컬 후보는 **문자열·값 프로파일·업무 지식으로 모든 허용 필드 쌍을 직접 점수화하는 LightGBM**이다. 합성 최종 1,132열에서 474개를 정확히 추천했고 오추천은 18건이었다. 추천 정밀도 **96.34%**(목표 ≥95%), 전체 오추천율 **1.59%**(≤5%), HOLD 거절 재현율 **95.18%**(≥95%)는 기준을 충족했다. Top-1 **60.85%**(≥85%)와 Top-3 **60.98%**(≥90%)는 목표 미달이었다. 완전 매핑 문서는 4/130개다. 실제 기업에서 검증한 뒤 운영 적용 여부를 결정한다.

- 환경은 Windows 10 22H2 x64, Python 3.11.9, Ryzen 5 5600G 6코어·12스레드, 물리 RAM 약 15.4 GiB, 확인 시 약 1.4 GiB 사용 가능, 작업 드라이브 여유 약 320 GiB였다. 내장 Radeon이 있고 모든 실험은 CPU로 진행했다.
- 고정 48건과 70건은 회귀 전용이다. 신규 학습·보정·최종 평가, 운영 API 및 승인 정책과 분리했다. [이전 BGE 비교](MAPPING_BGE_EVALUATION_20261122.md) · [이전 CPU 임베딩 비교](MAPPING_LOCAL_EMBEDDING_EVALUATION_20261123.md)
- 기존 RapidFuzz를 재실행해 48건의 Top-1 25/32·Top-3 26/32·오추천 3/48, 70건의 5/37·6/37·7/70을 재현했다. 11/23의 세 모델 문맥 수치는 해당 보고서의 역사적 결과다.

## 데이터와 실험 규약

| 분리 | 문서 | 컬럼 | 문서군 | 고정 SHA-256 |
| --- | ---: | ---: | ---: | --- |
| Train | 975 | 8,539 | 30 | `ff8293b843527ec1c2087af637d034bd92a19626bfdafd40429774c6390ec25e` |
| Calibration | 80 | 703 | 30 | `0ca04d71d809704a006bbdba237c79c3f56e92a01786939e79fd306b6a9fecee` |
| Final | 130 | 1,132 | 30 | `0609378f9e16a6ded396998f028d96f39ccae37c0a0bc2694442c2d3f8761850` |

현행 대상과 동일한 제품·자재·BOM·재고·월수요만 평가했다. CAPA, Routing, 판매 원장의 집계·변환은 별도 계약이다. 문서별 업무 열과 행을 먼저 생성한 다음 필드 정답과 HOLD를 부여했다. 문서 식별자, 템플릿 군, 언어별 헤더 어휘, 난수 seed, 코드 범위를 분리하고 문서별 CSV 바이트·split SHA를 기록했다. 정규화 헤더·파일 SHA의 교차 중복은 없었다. 같은 문서 유형 안에서 90점 이상인 교차 split 정규화 헤더 쌍도 0개였다. 통계 분포 생성 코드는 세 split에서 공유하므로 실제 기업 간 분포 이동을 대체하지 못한다.

최종 정답은 직접 매핑 779개와 HOLD 353개다. HOLD에는 거래처 65, 주문일 60, 금액 51, 알 수 없는 열 46, 잘못 제안된 문서 종류 43, 비고 42, 중복 10, 반품 9, 출고 8, 생산 7, 발주 7, 형식 불일치 5가 포함됐다. 필수 열 누락, 숫자형 헤더, 언어 혼용, 제목·주변열 충돌, 열 위치 변경과 누락값을 포함했다. 임베딩·LLM 입력의 `title`, `header`, 값·프로파일과 대상 후보는 입력에 있으며 정답·생성 역할·원본 문서종류 표기는 뺐다.

이훤님 XLSX 200개는 기존 독립 문서 레이아웃/분류 평가용이다. 평면 BOM 9개만 확인된 일부 컬럼 정답이 있다. 기존 보고서의 선택 범위 0/27→9/27을 참고하고 이번 열 매핑의 신규 정답으로 사용하지 않았다. 외부 독립 셋 SOTAB-SM과 NYU 벤치마크는 과제와 사용 조건을 검토했고 이번 실행에서는 제외했다. [기존 200개 검증](CLASSIFIER_XLSX_MAPPING_VERIFICATION_20261123.md) · [표 범위 검증](XLSX_TABLE_SELECTION_VERIFICATION_20261123.md)

### 채점·보정

- 원시 Top-1/3/5는 거절 전 후보 검색의 단계별 회수다. Top-1/3은 거절 뒤 정답 779개 대비고, 오추천은 다른 필드 또는 HOLD 열에 낸 추천 수를 전체 1,132열로 나눈다. 정밀도는 추천 중 정답, HOLD 거절 재현율은 HOLD 정답 353개에서 거절한 비율이다. 모든 필드에 해당하는 후보 쌍을 평가하고, 판별기에는 모든 HOLD의 허용 후보가 음성 쌍으로 들어간다.
- 동일한 형식·중복 및 운영 의미 검사를 공통 `allowed` 마스크에 적용했다. 제품 코드와 자재 코드, 금액과 수량 등 명백한 충돌을 차단하고 재고 산식·형식 적합성은 추가 신호로 사용했다. 기존 Exact/RapidFuzz 행은 기존 코드 자체의 결과다.
- Threshold와 Top-1/2 차이는 calibration에서만 설정했다. 95% 정밀도 조건을 만족하는 정책 중 정답 수를 최대화하며 조건을 충족하지 못하면 오추천에 벌점을 준다. `*-frozen.json`에 조건과 최종 SHA를 기록한 뒤 최종 분리를 읽는다. 최종 데이터의 risk–coverage 곡선은 진단용이다.
- 쌍 분류의 보정된 1순위 확률과 원시 유사도를 구분했다. 선택한 CPU 모델의 보정 검증은 최종 지원 컬럼 1,090개에서 Platt Brier 0.0961·ECE 0.0736, isotonic 0.0900·0.0354였다. 실제 운영 임계값은 별도 독립 검증 대상이다.
- 문서 단위 1,000회 paired bootstrap에서 LightGBM의 RapidFuzz 대비 정답 증가량은 전체 열 대비 **+34.1~+43.4%p**, 오추천 증가량은 **+0.75~+2.11%p**였다. 같은 생성 군의 문서가 서로 상관될 수 있어 실제 기업 차이의 신뢰구간으로 해석할 수 없다.

## 로컬 모델과 소거 실험

### CPU 경량 모델

| 방식 | 정확 Top-1 | 최종 Top-3 | 오추천 | HOLD | 정밀도 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Exact·별칭 | 0 | 0 | 0 | 1,132 | — |
| 운영 RapidFuzz | 34 | 34 | 2 | 1,096 | 94.44% |
| 문자 TF-IDF / 문자 BM25 | 0 / 0 | 0 / 0 | 0 / 0 | 1,132 / 1,132 | — |
| 3개 값의 타입 적합성 | 273 | 273 | 164 | 695 | 62.47% |
| 전체 열 통계 규칙 | 431 | 431 | 110 | 591 | 79.67% |
| 문자열·업무·값 규칙 | 276 | 276 | 18 | 838 | 93.88% |
| 통계·업무 규칙 | 101 | 101 | 4 | 1,027 | 96.19% |
| Logistic 문자열 | 0 | 0 | 1 | 1,131 | 0% |
| Logistic 통계 | 295 | 295 | 12 | 825 | 96.09% |
| Logistic 문자열+통계 | 283 | 283 | 14 | 835 | 95.29% |
| Logistic 문자열+통계+업무 | 403 | 403 | 15 | 714 | 96.41% |
| Logistic + 재고 산식 | 404 | 404 | 16 | 712 | 96.19% |
| 문자 TF-IDF → 필드+HOLD 다중 클래스 Logistic | 0 | 0 | 0 | 1,132 | — |
| Random Forest + 업무 | 308 | 308 | 17 | 807 | 94.77% |
| LightGBM 문자열 | 0 | 0 | 10 | 1,122 | 0% |
| LightGBM 통계+업무 | 449 | 462 | 20 | 663 | 95.74% |
| **LightGBM 문자열+통계+업무** | **474** | **475** | **18** | **640** | **96.34%** |
| LightGBM + 재고 산식 | 474 | 475 | 18 | 640 | 96.34% |
| CatBoost + 업무 | 40 | 40 | 2 | 1,090 | 95.24% |

전체 프로파일은 3개 값보다 정답 **+158**, 오추천 **−54**였다. Logistic에 통계와 업무 신호를 더하면 문자열 단독의 0건에서 403건으로 늘었다. 통계 단독과 통계+문자열은 이 split에서 업무 신호가 빠질 때 둘 다 덜 회수했다. LightGBM의 원시 후보에서는 정답 Top-3가 779/779이고, 보정 후 475/779다. 대다수 후보가 거절 또는 순위 판단 단계에서 소실됐다. TF-IDF 원시 Top-3 577, BM25 548이지만 보정 정책에서 두 방식 모두 추천이 없었다. 새로 작성한 비표준 어휘에서 Exact가 거절한 결과는 기존 별칭이 주로 등장하는 일반 입력에서의 커버리지와 다르다.

학습 전용 3-fold 검사는 문서군을 겹치지 않게 나눠 fold당 325문서를 사용했다. 전체 학습셋으로 미리 만든 분포 특징은 이 검사에서 제거했다. 거절 전 허용 후보의 정답 Top-1은 fold별 1,676/1,958, 1,688/1,978, 1,648/1,940이었다. 최종 판별 임계값은 독립 calibration 80문서에서 잠갔다.

### 전통 스키마 매칭

Valentine 1.0.1을 설치하고 학습셋 값만으로 표준 대표 테이블을 구성했다. Cupid/COMA-Instances는 미리 받은 NLTK 데이터를 로컬 경로에서 읽었다. COMA의 Python 매처를 사용했다.

| 방식 | Top-1 | 오추천 | HOLD | 상태 |
| --- | ---: | ---: | ---: | --- |
| COMA Schema | 0 | 0 | 1,132 | MEASURED |
| COMA Instances | 198 | 16 | 918 | MEASURED |
| Cupid | 22 | 17 | 1,093 | MEASURED |
| Similarity Flooding | 7 | 3 | 1,122 | MEASURED |
| Jaccard | 161 | 3 | 968 | MEASURED |
| DistributionBased | — | — | — | FAILED. 내부 분포 군 이름 조회 `ValueError` |

기준값이 겹치는 정답 열은 292개, 겹치지 않는 정답 열은 487개였다. COMA Instances는 각각 164/292·34/487, Jaccard는 161/292·0/487이었다. 동일한 의미에 서로 다른 기업 코드가 들어가는 입력에서 단순 값 일치가 취약함을 확인했다.

### 전역 제약과 사용자 이력

- LightGBM 독립 추천의 중복 열은 6개였다. Greedy와 Hungarian 모두 중복 0개, 정확 468, 오추천 18, HOLD 646이었다. 후보마다 전용 HOLD 노드를 사용해 필수 필드의 빈 자리를 강제로 채우지 않았다. 필수 매핑 재현율은 61.40%→60.40%, 누락 필드 탐지는 모두 90.41%였다. 문서 전체 일치가 4개로 같은 만큼 기본은 독립 추천 + 충돌 검토가 적합하다.
- `현재고 - 할당 = 가용`의 값 일치는 역할 판별에 보조적으로 썼다. 대칭 때문에 할당과 가용을 바꿔도 식이 성립할 수 있다. 재고 산식의 Logistic 개선은 정답 +1·오추천 +1, LightGBM 결과는 동일했다. 판매수량×단가, BOM 참조 키, CAPA/Routing 관계의 효과는 이번 수치에 포함되지 않는다.
- 이력은 별도 80개 합성 재업로드 시나리오에서만 평가했다. 데이터셋·엔터티·스키마 버전·헤더 순서를 키로 쓰고 사용자 확정만 보관했다. 다른 데이터셋, 취소, 버전 변경은 이력에서 제외했다. 앱 추천과 상충·중복 가능성이 있으면 사용자에게 다시 표시할 필요가 있다.

| 80개 재업로드 시나리오, 721열 | 정확 | 오추천 | 문서당 수정 필요 열 |
| --- | ---: | ---: | ---: |
| RapidFuzz | 44 | 14 | 5.96 |
| 일치 이력 | 149 | 31 | 4.65 |
| 유사 이력 | 213 | 29 | 3.85 |
| 유사 이력 + 형식·현재 후보 충돌 확인 | 186 | 24 | 4.19 |

사용자가 확정했지만 의미상 잘못된 이력도 재사용 시 전달됐다. 이력 조회는 검토 신호로 제한하고 업체·버전 경계를 유지하는 편이 적합하다. 새 기업 최종 셋의 LightGBM 성능에는 이 수치가 섞이지 않는다.

### 임베딩·Reranker·로컬 LLM

공식 E5-small ONNX FP32와 `query:`/`passage:`의 mean pooling을 재사용했다. 표준의 HOLD 설명을 별도 위치로 두고 `필드 유사도 − HOLD 유사도`를 calibration에서 판별했다. E5 파일·토크나이저 합계 487 MB. mMiniLM은 저자 제공 ONNX int8 119 MB, ONNX Runtime CPU 경로다. [E5 카드](https://huggingface.co/intfloat/multilingual-e5-small) · [mMiniLM Apache-2.0 카드·ONNX](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1/tree/main/onnx)

| 동일 헤더 입력, 최종 1,132열 | 원시 Top-1 / 3 / 5 | 정확 Top-1 | 최종 Top-3 | 오추천 | HOLD | 정밀도 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BGE-M3 Q4 ONNX | 558 / 755 / 778 | 205 | 228 | 59 | 868 | 77.65% |
| Qwen3-Embedding-0.6B Q8_0 | 536 / 714 / 754 | 164 | 189 | 28 | 940 | 85.42% |
| E5-small FP32 ONNX | 359 / 577 / 714 | 12 | 12 | 0 | 1,120 | 100% |

BGE의 공개 Q4 ONNX 변환은 CLS, 공식 Qwen Q8_0은 instruction+last pooling을 사용했다. Q4는 기존 보고서의 BGE FP32와 별도 결과다. BGE와 Qwen 전체 문맥은 보정·일부 검증 벡터를 캐시한 뒤 CPU 시간을 고려해 중단했다. 최종 전체 문맥 수치는 `NOT_RUN`이며 현재 명령에 `--modes header full`을 추가하면 캐시에서 재개한다. E5는 8가지 조건을 끝까지 실행했다. [BGE 원본 카드](https://huggingface.co/BAAI/bge-m3) · [Q4 ONNX 배포](https://huggingface.co/Xenova/bge-m3/tree/4de13258303883538bd53b696b452bf8099f0858) · [Qwen Embedding GGUF 카드](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF)

| E5 문맥/학습 | 원시 Top-3 | 정확 Top-1 | 최종 Top-3 | 오추천 |
| --- | ---: | ---: | ---: | ---: |
| 헤더 | 577 | 12 | 12 | 0 |
| 자료형 | 552 | 10 | 10 | 0 |
| 샘플 값 | 606 | 12 | 12 | 0 |
| 통계 프로파일 | 510 | 49 | 61 | 27 |
| 주변 컬럼·제목 | 428 | 22 | 22 | 0 |
| 전체 문맥 | 545 | 8 | 8 | 0 |
| 전체+업무 | 572 | 0 | 0 | 0 |
| 전체+혼동 필드 | 566 | 16 | 16 | 0 |
| 동결 E5 + 쌍 Logistic | 577 | 111 | 141 | 53 |
| 동결 E5 + 문자열/통계/업무 head | 779 | 47 | 47 | 0 |
| 동결 E5 + 학습 투영층 | 602 | 88 | 88 | 2 |
| 동결 E5 + 학습 투영층 + 쌍 분류기 | 779 | 41 | 41 | 0 |

투영층은 동결 E5의 384×384 매트릭스를 장착해 Train 8,539열에서 ridge로 적합시켰다. 학습 파라미터 147,456개, 가중치 약 1.18 MB, 적합 약 0.10초, 훈련 MSE 0.0001903이다. 헤더 기준 12→88개, 오추천 0→2건으로 개선됐다. 원본 encoder, transformer, LoRA/PEFT, GNN의 가중치 재학습은 이번 CPU에서 미실행이다. 이 수치는 동결 인코더에 추가한 경량 층의 결과다.

| mMiniLM 비교 구조 | 원시 Top-1 / 3 / 5 | 정확 Top-1 | 최종 Top-3 | 오추천 |
| --- | ---: | ---: | ---: | ---: |
| 모든 필드 쌍 + HOLD | 400 / 617 / 690 | 0 | 0 | 0 |
| RapidFuzz 후보 제한 | 32 / 34 / 34 | 0 | 0 | 0 |
| E5 전체 문맥 Top-3 → mMiniLM | 353 / 545 / 545 | 0 | 0 | 0 |
| BGE-M3 Q4 헤더 Top-3 → mMiniLM | 463 / 755 / 755 | 48 | 50 | 2 |
| Qwen3 Embedding Q8_0 헤더 Top-3 → mMiniLM | 449 / 714 / 714 | 49 | 52 | 3 |
| LightGBM Top-3 → mMiniLM | 535 / 779 / 779 | 69 | 78 | 9 |

mMiniLM의 후보 재판별은 BGE의 오추천을 59→2로, Qwen의 오추천을 28→3으로 줄였고 정확 추천도 각각 205→48, 164→49로 감소했다. LightGBM 후보 재판별의 정밀도는 88.46%였다. 전체 쌍을 계산한 캐시에 후보 마스크를 적용해 정확도를 비교했다. 후보 제한 실행 자체의 지연 감소는 측정하지 않았다. BGE-reranker-v2-m3와 Qwen3-Reranker-0.6B는 원본 모델과 라이선스를 확인했고 이 CPU 실행에서는 mMiniLM과 분리해 `NOT_RUN`으로 둔다. [BGE-Reranker 카드](https://huggingface.co/BAAI/bge-reranker-v2-m3) · [Qwen3-Reranker 카드](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)

로컬 생성형 Qwen3-0.6B는 공식 Q8_0 약 639 MB와 llama.cpp `b12657`을 사용했다. 최종 셋에서 유형별 첫 2문서로 미리 정한 작은 패널이다. 컬럼 단독 10회와 전체 문서 10회에서 각각 완전한 계약 응답은 **1/10**이었고 정답 추천은 0건이었다. 전체 표 패널은 85열이며 직접 매핑 정답은 60개다. JSON 파싱·구조 검증 실패와 35초 타임아웃을 별도로 기록했다. 실패 요청은 유효 추천을 내지 않았고 필드 검사를 완화하지 않았다. RapidFuzz 제한 소형 패널은 후보가 없어 호출 0건으로 비교하지 못했다. 대형 모델이나 다른 프롬프트의 성능을 추정하지 않는다. [Qwen 모델 카드](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF) · [llama.cpp 릴리스](https://github.com/ggml-org/llama.cpp/releases/tag/b12657)

### 실행 시간과 메모리

| 단계 | 시간 | 단위·포함 범위 |
| --- | --- | --- |
| Exact | P50 0.08 ms / P95 0.20 ms | 문서당 매핑 |
| 운영 RapidFuzz | P50 1.41 ms / P95 3.50 ms | 문서당 프로파일과 추천 |
| 공통 CPU 특징 | P50 7.09 ms / P95 23.27 ms | 문서당 특징 계산 |
| LightGBM | P50 0.09 ms / P95 0.38 ms, 학습 0.23 s | 문서당 특징 생성 이후 추론 |
| Valentine COMA Instances / Jaccard | P95 74.85 ms / 18.07 ms | 문서당 매칭 |
| E5 헤더 / 전체 문맥 | P50 4.47 / 22.81 ms, P95 5.76 / 30.72 ms | 고유 입력 1개당 배치 평균 |
| BGE Q4 헤더 | P50 93.39 ms / P95 124.19 ms | 고유 입력 1개당 배치 평균 |
| Qwen3 임베딩 헤더 | P50 172.85 ms / P95 188.86 ms | 고유 입력 1개당 배치 평균 |
| mMiniLM | P50 1.83 s / P95 7.45 s | 문서당 모든 필드 쌍과 HOLD 추론 |
| 로컬 LLM 컬럼 / 문서 | P50 7.58 / 12.80 s, P95 11.44 / 35.01 s | 요청당, 실패 시간 포함 |

CPU 실험 전체 24.62초·최대 RSS 약 257 MiB, Valentine 전체 71.61초·408 MiB였다. E5 전체 104.99초·1,200 MiB, BGE 헤더 약 2,558 MiB, mMiniLM 캐시 재실행 약 594 MiB를 관측했다. E5/BGE/mMiniLM의 초기화는 각각 약 2.76/4.18/1.35초였다. llama.cpp 하위 프로세스를 포함한 Qwen 최대 메모리는 측정하지 않았다. 측정 단위와 포함 범위가 다른 행의 시간을 직접 나눠 속도 배율을 계산할 수 없다.

## Upstage 준비와 비용

2026-11-24 공식 문서를 기준으로 `solar-embedding-2-query`/`solar-embedding-2-passage`는 1,024차원, 최대 배열 100개, 모델당 100 RPM·300,000 TPM이다. 비교 Snapshot은 `solar-mini4-260922`, `solar-pro4-260806`이며 Chat API의 JSON Schema 응답을 사용한다. Solar Pro 3와 Pro 2의 공시된 종료일은 2026-10-30 KST, 기존 Embedding 1은 2026-12-31 UTC 종료 예정이다. [임베딩 모델](https://console.upstage.ai/docs/capabilities/embed) · [임베딩 API](https://console.upstage.ai/api/embeddings) · [Chat API](https://console.upstage.ai/api/chat) · [공식 가격](https://www.upstage.ai/pricing/api)

| 고정 최종 1,132열 | 요청 | 입력 토큰 상한 추정 | 출력 토큰 상한 | 예상 USD (세전) |
| --- | ---: | ---: | ---: | ---: |
| Embedding 2 단독 | 24 | 305,441 | 0 | 0.0061 |
| Mini 4 컬럼 단독 | 1,132 | 3,653,680 | 72,448 | 0.3943 |
| Mini 4 전체 문서 | 130 | 695,101 | 36,224 | 0.0840 |
| Mini 4 업무 지식+문서 | 130 | 765,277 | 36,224 | 0.0910 |
| Pro 4 컬럼 단독 | 1,132 | 3,652,548 | 72,448 | 1.1827 |
| Pro 4 전체 문서 | 130 | 694,971 | 36,224 | 0.2520 |
| Pro 4 업무 지식+문서 | 130 | 765,147 | 36,224 | 0.2730 |

비용은 요청의 UTF-8 직렬화 길이+고정 여유와 최대 출력으로 계산한 보수적 **견적**이다. 별도 calibration 호출 비용은 위 표에 포함되지 않는다. 토크나이저 실측, 청구·응답 속도·정확도는 `NOT_RUN`이다. 실제 API 요청·청구는 0건이며 API 실행기에 키를 전달하지 않았다. 실행기는 고정 합성 split SHA, 승인 및 양수 비용 상한, 요청·응답 SHA, 캐시 잠금, 토큰 기록, ID/필드 제한을 검사한다. 네트워크 실패는 예약 비용을 유지하며 자동 재시도하지 않는다. 승인 전 `plan`/`export`만 실행했다.

## 최종 아키텍처 비교와 적용 판단

`MEASURED`는 실행한 표본에서만 유효하다. `FAILED`는 실행 중 오류, `NOT_RUN`은 성능 수치가 없는 구성이다.

| ID | 구조 | 상태와 관찰 |
| --- | --- | --- |
| A01 | RapidFuzz | MEASURED, 34 정답·2 오추천 |
| A02 | 전통 스키마 매칭 | MEASURED, COMA Instances 198·16, Jaccard 161·3. DistributionBased FAILED |
| A03 | 통계+업무 규칙 | MEASURED, 101·4 |
| A04 | 문자열+LightGBM | MEASURED, 0·10 |
| A05 | 통계+업무 LightGBM | MEASURED, 449·20. 문자열을 더한 전체 CPU 조합 474·18 |
| A06 | BGE-M3 | MEASURED Q4 헤더 205·59. 공식 FP32는 기존 기록. 신규 전체 문맥 NOT_RUN |
| A07 | E5-small | MEASURED, 8개 문맥 소거. 전체 문맥 8·0 |
| A08 | Qwen3 Embedding | MEASURED Q8_0 헤더 164·28. 신규 전체 문맥 NOT_RUN |
| A09 | 임베딩 + 판별기 | MEASURED, E5 혼합 head 47·0, E5 점수만 쓴 head 111·53 |
| A10 | 후보 검색 + Reranker | MEASURED, mMiniLM과 RapidFuzz/E5/BGE 헤더/Qwen 헤더/LightGBM 후보 결합. LightGBM→mMiniLM 69·9 |
| A11 | 도메인 임베딩 학습 | MEASURED, 동결 E5 + 학습 투영층 88·2. encoder 가중치 학습은 NOT_RUN |
| A12 | 학습 임베딩 + 판별기 | MEASURED, 위 투영층 + 쌍 분류기 41·0 |
| A13 | 로컬 LLM 단독 | MEASURED 소형 패널, 컬럼 요청 10건 중 구조 검증 통과 1건 |
| A14 | 로컬 LLM 전체 테이블 | MEASURED 소형 패널, 10문서 중 구조 검증 통과 1건 |
| A15 | 로컬 후보 검색 + LLM | NOT_RUN. 소형 패널의 RapidFuzz 후보가 없어 실제 호출 없음 |
| A16 | Upstage Embedding 2 | NOT_RUN, 테스트 입력·비용·임계값 채점 경로 준비 |
| A17 | Solar 컬럼 직접 판별 | NOT_RUN, JSON Schema 요청 준비 |
| A18 | Solar 전체 테이블 | NOT_RUN, 표 단위 요청과 중복 검사 준비 |
| A19 | RapidFuzz + Solar | NOT_RUN, 제한 후보 JSON 입력 |
| A20 | 로컬 임베딩 + Solar | NOT_RUN, 로컬 후보 출력과 제한 후보 입력 준비 |
| A21 | 지도학습 판별기 + Solar | NOT_RUN, CPU 후보 출력과 제한 후보 입력 준비 |
| A22 | Upstage Embedding + Solar | NOT_RUN, 개별 실행기 준비. 실제 혼합 연결 검증은 승인 뒤 진행 |
| A23 | 업무 지식 + Solar | NOT_RUN, 업무·혼동 필드 조건을 포함한 문서 요청 준비 |

**정확도와 작업량.** CPU 전체 쌍 LightGBM이 측정한 구조 중 가장 많은 정답을 승인 후보에 올렸다. 생산 코드의 사용자 검토·검증·승인 흐름을 유지하고, 새로운 기업에서 후보만 출력하는 shadow 비교가 다음 MVP 단계다. 정확한 이름·기존 별칭은 운영 규칙을 재사용하고, 낯선 열에만 CPU 후보를 붙이는 버전은 독립 실험에서 확인한다. 필드 타입·중복·다른 데이터셋의 이력 충돌은 검토 사유를 반환한다.

**속도와 최소 오류.** 매퍼만 측정하면 Exact가 가장 빠른 운영 기준선이었다. 현재 합성 최종의 비표준 표현에서는 전부 HOLD였다. 덜 공격적인 선택은 Jaccard 161·3이나 통계·업무 규칙 101·4였고, 값이 겹치지 않는 표에서는 Jaccard가 정답을 찾지 못했다. 매핑량과 오추천의 Pareto 비교에서 LightGBM 474·18이 커버리지를 확보하며 정밀도 목표를 넘긴 쪽이고, Jaccard 161·3과 E5 투영층 88·2는 오류 비용을 더 높게 잡을 때의 점이다. 유료 API 비용 정보는 예상치라 비용 대비 성능 순위에서 제외했다.

**비용 대비 효율.** 추가 API 비용 없이 정밀도 95% 이상으로 가장 많은 정답을 제안한 구성은 LightGBM이었다. 이 결론은 이번 CPU에서 관측한 계산 시간과 합성 데이터 성능에 한정한다. 기업별 라벨링, 유지보수, 검토 인력 비용은 측정하지 않았다.

**오류의 실제 구성.** CPU 선택 모델 18건은 거래처 코드 7건, 잘못 들어온 문서 종류 6건, 발주량 4건, 정답 있는 열의 혼동 1건이었다. 예를 들어 `invoice party ref`가 `bom_id`로, 재고로 분류된 BOM의 `assembly component tier`가 `item_type`으로 추천됐다. 130문서 중 수동으로 수정하거나 확인할 열은 평균 2.48개였고 RapidFuzz는 5.75개였다. 보정셋에서 차이가 가장 모호한 67개를 우선 확인하면 66개가 오추천 후보 또는 매핑 대상이 없는 열이었다. 이 시뮬레이션은 검토 우선순위이며 사용자 정답 재학습 결과는 아니다.

**한계와 현장 검증.** 합성 표의 값 범위·일부 포맷이 공유되고, 정확 별칭의 비중이 실제 업로드와 다르다. 독립 제조 템플릿을 업체·양식 단위로 모으고 작업자 2명이 각자 정답과 HOLD를 판단한 뒤 분쟁 사례를 별도로 판정한다. 실제 필요한 수동 작업과 틀린 추천의 비용을 식별할 수 있도록 필수 항목, 문서 분류 오류, 시트·헤더 선택 오류, 변환 필요 문서를 별도 집계한다. 임계값과 모델군을 먼저 잠근 후 신규 업무 문서 정밀도와 역할별 HOLD, 수정량을 평가한다. 기존 별칭·HOLD·승인의 신호는 운영과 동등한 인수 시험으로 확인한다.

## 재현

PowerShell에서 저장소 루트 기준. 의존성과 NLTK 구문 자료는 기계의 운영 Python 패키지와 분리한다.

```powershell
$research = Join-Path $PWD '.artifacts/mapping-research'
.\.venv\Scripts\python.exe -m pip install --target "$research/deps" -r scripts/mapping_research_requirements.txt
$env:PYTHONPATH = "$research/deps"
$env:NLTK_DATA = "$research/nltk"
$env:OPENBLAS_NUM_THREADS = '2'
$env:OMP_NUM_THREADS = '2'
.\.venv\Scripts\python.exe scripts/evaluate_mapping_research.py generate --write-csv
.\.venv\Scripts\python.exe scripts/evaluate_mapping_research.py cpu --threads 2
.\.venv\Scripts\python.exe -m nltk.downloader -d $env:NLTK_DATA wordnet omw-1.4 stopwords punkt_tab
.\.venv\Scripts\python.exe scripts/mapping_research_classical.py valentine
.\.venv\Scripts\python.exe scripts/mapping_research_classical.py memory
.\.venv\Scripts\python.exe scripts/evaluate_mapping_recommendations.py --output "$research/results/regression48.json"
.\.venv\Scripts\python.exe scripts/evaluate_mapping_embeddings.py --method rapidfuzz --output "$research/results/regression70.json"
.\.venv\Scripts\python.exe scripts/mapping_research_remote.py plan --mode table --split final --output "$research/results/upstage-estimate.json"
.\.venv\Scripts\python.exe scripts/mapping_research_remote.py export --mode table --split calibration --output "$research/results/upstage-calibration-input.json"
.\.venv\Scripts\python.exe -m pytest --no-db -q --tb=short
```

모델·캐시는 `.artifacts/mapping-research/`에만 둔다. 새 모델 조합을 선택하거나 알고리즘을 수정할 때는 이 최종 셋 대신 새로운 독립 표를 고정한다.

### 검증과 변경 범위

- 2026-11-24 보조 PC에서 `pytest --no-db -q --tb=short` **1,252 passed / 0 failed / 68 skipped**. 연구 회귀 13건과 기존 OpenAPI·JSON Schema 동기화 검사를 포함한다. Starlette 테스트 클라이언트 사용 중 기존 사용 중단 경고 1건이 나왔다.
- 프로젝트 보안 검사에서 연구 변경 15개 파일의 탐지 0건. 운영 앱, API 계약, 인프라, 프론트엔드, 팀 모듈의 Git diff는 비어 있다. Docker·DB와 유료 공급사 검증은 미실행이다.
- 주요 변경은 `scripts/mapping_research_*.py`, `scripts/evaluate_mapping_research.py`, `scripts/evaluate_mapping_embeddings.py`, `backend/tests/test_mapping_research.py`, 문서 4개다. 완료 Commit 조회 명령은 [개발 이력](DEVELOPMENT_CHANGELOG.md)에 기록했다.

### 공개 모델과 저장소 검증

```powershell
$model = "$research/models"
$results = "$research/results"
$llama = "$model/llama/llama-server.exe"
.\.venv\Scripts\python.exe scripts/mapping_research_neural.py e5 --model "$model/e5" --threads 2 --batch 12
.\.venv\Scripts\python.exe scripts/mapping_research_neural.py minilm --model "$model/minilm" --threads 2 --batch 24
.\.venv\Scripts\python.exe scripts/mapping_research_neural.py bge-q4 --model "$model/bge-q4" --threads 1 --batch 4 --modes header
.\.venv\Scripts\python.exe scripts/mapping_research_neural.py qwen --model "$model/qwen-embedding.gguf" --llama $llama --threads 2 --batch 16 --modes header
.\.venv\Scripts\python.exe scripts/mapping_research_hybrid.py "$results/e5-scores.json" "$results/cpu-selected-scores.json" "$results/bge-q4-scores.json" "$results/qwen-scores.json"
.\.venv\Scripts\python.exe scripts/mapping_research_local_llm.py --model "$model/qwen-instruct.gguf" --llama $llama --threads 2
```

`e5`는 `intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3`의 `onnx/model.onnx`와 루트 `tokenizer.json`이다. `minilm`은 `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1@1427fd652930e4ba29e8149678df786c240d8825`의 `onnx/model_quint8_avx2.onnx`, `bge-q4`는 표의 링크 리비전 `onnx/model_q4.onnx`를 각각 `model.onnx`로 저장한다. 두 디렉터리에 해당 `tokenizer.json`과 전체 리비전 문자열을 `revision.txt`로 기록한다. Qwen 임베딩은 `Qwen/Qwen3-Embedding-0.6B-GGUF@370f27d7550e0def9b39c1f16d3fbaa13aa67728`, 생성형은 `Qwen/Qwen3-0.6B-GGUF@23749fefcc72300e3a2ad315e1317431b06b590a`의 `Q8_0` 파일이다. llama.cpp는 `b12657` Windows x64 CPU 자산이다.
