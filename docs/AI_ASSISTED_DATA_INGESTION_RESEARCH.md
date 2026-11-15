# AI 보조형 데이터 입력 연구와 1차 설계 판단

작성·원문 확인: 2026-11-15. 구현 전 연구 기록. 기준 main `ff448ace16aa58d4fb963bac6ab52841966b72fa`. 아래는 논문의 보고 결과와 충파모의 설계 판단을 분리한다. 의료·금융·공공 벤치마크의 성능을 한국 제조업 파일의 성능으로 간주하지 않는다. 연구 결과를 자체 재현한 것은 아니다.

## 논문 5편

### 1. LLMATCH (2025)

[초록](https://arxiv.org/abs/2507.10897), [원문 v1 §4–6, 표 1–3](https://arxiv.org/html/2507.10897v1).

- 문제·방법: 복잡한 관계형 스키마의 의미 대응. schema preparation → table-candidate selection → column alignment로 분리하고 Rollup/Drilldown으로 관계 구조를 단순화·복원한다.
- 실험·지표: 기존 단순 task와 의료·금융·엔터테인먼트 SchemaNet 7쌍, F1 및 구조/컨텍스트 ablation. GPT-3.5-turbo/GPT-4o-mini 및 SBERT를 사용했다.
- 확인 수치: §6.4의 mimic_iii-omop 예시는 LLMatch F1 0.40, ReMatch 0.20. 이는 해당 task 결과이며 전체 평균/제조업 정확도가 아니다.
- 한계: LLM 비결정성, 문맥 길이·스키마 설명/관계 의존성, 소규모 사용자 실험. 임의 CSV 의미 해석을 보장하지 않는다.
- 적용 판단: 파일 종류 분류(이훤)와 엔터티 내부 컬럼 추천(백엔드)을 분리한다. 지금은 관계형 Rollup/Drilldown이나 LLM 기반 table selection을 구현하지 않는다. 파일 분류 결과로 승인 게이트를 우회하지 않는다.

### 2. Schema Matching with Large Language Models: an Experimental Study (2024)

[초록](https://arxiv.org/abs/2407.11852), [원문 v1 §2–3, 표 1–2](https://arxiv.org/html/2407.11852v1).

- 문제·방법: 이름·설명만으로 semantic match를 찾는 GPT-3.5/GPT-4의 task scope(1:1/1:N/N:1/N:M)와 N-gram 문자열 baseline을 비교한다. 데이터 인스턴스 기반 실험과 구분해야 한다.
- 실험·지표: 의료 MIMIC-IV→OMOP 9쌍, 1,839 attribute pairs/정답 49개. F1·precision/recall·결정성·일관성·검토 노력을 측정한다.
- 확인 수치: 표 2 AdVO median F1은 문자열 baseline 0.333, GPT-4 N-to-1 0.636. scope별 차이가 커서 ‘LLM 정확도’ 한 숫자로 일반화할 수 없다.
- 한계: 맥락 부족과 과다 모두 품질을 저하시킬 수 있고 추천 검증에도 비용이 든다. 의료 명칭의 결과를 제조업 한글 컬럼에 옮겨 붙일 수 없다.
- 적용 판단: 먼저 정확 별칭을 보존하고 top-k 근거를 제한한다. 헤더만 보고 날짜·금액·수량 의미를 확정하지 않는다. 추천당 검토 필요 여부와 HOLD/수정 비용을 벤치마크로 남긴다.

### 3. Schemora (2025)

[초록](https://arxiv.org/abs/2507.14376), [원문 v1 §3–5, 표 2–3](https://arxiv.org/html/2507.14376v1).

- 문제·방법: 전체 pairwise 비교 비용. LLM으로 metadata/name을 보강하고 lexical·vector retrieval 및 다단계 추천으로 후보를 줄인다. 표의 generated-name 수와 사용자 표시 후보 수를 혼동하지 않는다.
- 실험·지표: MIMIC-OMOP 중심, SYNTHEA-OMOP 추가 평가, HitRate@1/@3/@5 및 ablation. GPT-4.1과 임베딩 조합을 비교했다.
- 확인 수치: 표 3 MIMIC-OMOP HitRate@1 54.25%, @3 72.55%, @5 80.39%. ReMatch @5 72.90%와의 차이는 7.49 percentage points다. 문단의 @3 오기(72.05) 대신 표 72.55를 인용한다.
- 한계: top-k에 정답 존재는 자동 매핑 성공과 다르다. metadata 생성/embedding 비용과 의료 도메인 의존성이 남는다.
- 적용 판단: 작은 표준 필드 집합에는 새 vector 인프라를 도입하지 않는다. 규칙 top-3 성능·사용자 수정량을 먼저 측정하고 향후 임베딩→미해결 LLM 순서를 비교한다.

### 4. AutoDCWorkflow (EMNLP 2025)

[공식 논문 페이지](https://aclanthology.org/2025.findings-emnlp.410/), [공식 PDF §4–5, 표 4/8](https://aclanthology.org/2025.findings-emnlp.410.pdf).

- 문제·방법: 분석 목적에 필요한 최소 clean table을 만들도록 OpenRefine 연산을 순서대로 제안한다. upper/trim/numeric/date/mass_edit/regexr_transform 6종을 사용한다.
- 실험·지표: 6개 주제, 96 tables, 142 purposes. 사람이 만든 정답 table/workflow와 answer·column-value·operation quality를 별도로 평가했다.
- 확인 수치: 표 8 Flights의 Gemma2-27b는 DP→AutoDCWorkflow에서 Answer F1 **0.4842→0.4842**, Column Similarity **0.5081→0.6586**이다. 값 정제와 분석 정답 개선은 다른 지표이며 모든 차원이 향상된다는 주장을 하지 않는다.
- 한계: 소규모 표·삽입 오류·분석 목적 조건의 실험이며, 대량 제조 원장의 정책 판단을 보장하지 않는다.
- 적용 판단: 제안과 실행을 분리하고 허용 연산/버전/원본 SHA/제외 근거를 남긴다. 논문의 자유로운 정규식/LLM 반복 실행은 지금 도입하지 않는다. 사용자 확인 전 저장·승인은 없다.

### 5. Towards Scalable Schema Mapping using Large Language Models (2025)

[초록](https://arxiv.org/abs/2505.24716), [원문 v1 §3–6, 표 1–2](https://arxiv.org/html/2505.24716v1).

- 문제·방법: 입력 표현에 따른 출력 불일치, GLaV 등 표현력, 반복 호출 비용. 대칭 입력 변형·sampling/aggregation·양방향 matching과 타입/제약 기반 filtering을 검토한다.
- 실험·지표: MIMIC/Synthea, Llama-3.1-70B-Instruct-GPTQ-INT4, 3 seeds 평균 P@k/R@k/F1@k. 비교 방법의 전처리 조건도 명시했다.
- 확인 수치: 표 1 MIMIC bidirectional stable matching k=1은 P 0.68/R 0.62/F1 0.64. aggregation original은 P 0.35/R 0.79/F1 0.47. 후보 선택은 precision/recall trade-off다.
- 한계: 초기 실험·표현/도메인·모델 제한, 여러 호출 비용과 외부 API privacy 우려. 임의 변환 실행의 정당성을 주지 않는다.
- 적용 판단: 숫자/날짜/코드·마스터 타입으로 후보를 먼저 거르고 입력·정책 digest를 보존한다. 모델 출력 일관성을 승인 근거로 삼지 않는다. 현재 sampling/LLM 호출은 0회다.

## 공식 솔루션 검토

- **Power Query:** [fuzzy matching 공식 문서](https://learn.microsoft.com/en-us/power-query/fuzzy-matching)는 유사도 threshold(기본 0.8), transformation table, applied steps를 설명한다. 이 값은 문자열 유사도 설정이지 정답 확률이 아니다. 충파모는 후보 생성/사용자 변환표의 개념만 채택하며 0.8/0.95를 신뢰도로 복제하지 않는다.
- **OpenRefine:** [매뉴얼](https://openrefine.org/docs), [변환](https://openrefine.org/docs/manual/transforming), [실행·history](https://openrefine.org/docs/manual/running). facet/filter/cluster와 작업 이력으로 사람이 정제하는 흐름이다. 기본 기능은 로컬 실행 가능하지만 reconciliation/웹 확장은 전송 정책이 따로 필요하다. 충파모는 원본 불변·검토 가능한 작업 순서를 채택하고 GREL/임의 코드 실행은 노출하지 않는다.
- **Great Expectations:** [유일성/복합키 공식 가이드](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/uniqueness/)는 single/compound uniqueness와 unexpected-value 근거를 제공한다. [데이터 품질 사례](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/uniqueness/#avoid-common-uniqueness-analysis-pitfalls)의 completeness/schema와 함께 판단해야 한다. 충파모는 기존 행·셀 검증을 재사용한다. 월 수요의 동일 중복 경고·제거 정책을 GX식 ‘모든 중복 오류’로 바꾸지 않는다. 새 dependency는 도입하지 않는다.
- **AWS Glue DataBrew:** [개요](https://docs.aws.amazon.com/databrew/latest/dg/what-is.html), [profile jobs](https://docs.aws.amazon.com/databrew/latest/dg/jobs.profile.html), [quality rules](https://docs.aws.amazon.com/databrew/latest/dg/profile.data-quality-rules.html), [versioned recipes](https://docs.aws.amazon.com/databrew/latest/dg/recipes.html)를 확인했다. profile/recipe/ruleset 분리 및 재사용 버전을 참고한다. S3/IAM/job 인프라·서비스 비용이 추가되므로 현재 도입하지 않는다. 마케팅 절감률을 우리 성능으로 인용하지 않는다. 잘못된 profile.data.html 경로 대신 공식 jobs.profile.html을 사용했다.

## 솔루션 비교 (충파모 적용 관점의 판단)

| 평가 기준 | Power Query | OpenRefine | Great Expectations | DataBrew | 충파모 1차 |
| --- | --- | --- | --- | --- | --- |
| 컬럼명 매칭 | fuzzy merge는 주로 값 매칭, 스키마 자동 의미 매칭 아님 | 수동/클러스터·reconcile | 명시한 기대 schema | 변환 recipe | 별칭 보존 + 문자열 후보 |
| 값 기반 분석 | 타입/변환 | facet·cluster | 검증 통계 | profile jobs | bounded profile·타입·참조 비율 |
| 의미 추천 | 본 문서 기능만으로 LLM 주장 불가 | 확장 별도 | 검증 엔진, 의미 매칭 아님 | smart suggestions가 의미 보증은 아님 | LLM/embedding 미연결 |
| 자동 변환 | applied steps | 사용자 선택 작업 | 검증 중심 | recipe | 고정 허용 연산·Decimal |
| 사용자 확인 | 편집 가능 | 사용자 중심 | 규칙 설정 필요 | recipe/rules 설정 | 정책 확인 필수, 자동 승인 없음 |
| 근거 | steps/유사도 | facet/history | validation results | profile/rule 결과 | 위치·제외 건수·합계·SHA |
| 재현성 | 고정 단계/입력 조건 | 고정 history/입력 조건 | 고정 expectations | recipe version | 고정 정책·mapping·입력 digest |
| 비용 | 제품/실행 환경별 | 로컬 자원/확장 | Core 실행 자원, Cloud 별도 | cloud job·storage | 추가 모델/인프라 비용 없음 |
| 개인정보 | 연결·배포 정책 필요 | 기본 로컬, 외부 확장 주의 | 배포/백엔드에 따라 | AWS 전송/권한 검토 | 외부 전송 없음, 샘플 기본 미노출 |
| 구현 난이도 | 서비스 안 이식 별도 | 별도 앱/연산 호환 | 기존 validator 중복 가능 | S3/IAM/job 추가 | 기존 FastAPI 파서 확장 |

## 구현 결정과 후속 조건

규칙은 타입/형식·참조 검증, 고정 변환, Decimal 합계를 담당한다. AI는 향후 미해결 entity/column/operation **추천**만 담당한다. 사용자는 주문/출고 날짜·취소/반품·단위·중복 정책을 확정한다. 최종 승인자는 기존 gate를 거친다.

현재 구현할 것은 bounded profiling, exact/strong/weak 보존, top-3 fuzzy 후보와 반증, HOLD, 합성 판매 원장의 월 집계 미리보기다. 작은 표준 vocabulary에는 표준 라이브러리 `difflib.SequenceMatcher`를 사용해 새 설치 비용을 피한다. RapidFuzz는 다수 후보에서 실행시간 측정 후 검토한다. 문자열 점수는 정확도/신뢰도가 아니며 응답에 가짜 confidence를 내보내지 않는다.

저장 매핑 규칙은 DTO 인터페이스만 마련하고 DB migration은 하지 않는다. 원본/변환 정책/실행 기록의 영구 보관과 통제된 다운로드·대량 추적은 후속이다. 상세 계약은 구현과 함께 [AI 후속 설계](AI_MAPPING_INTEGRATION_DESIGN.md), [자체 벤치마크](DATA_INGESTION_BENCHMARK.md)에 동기화한다.
