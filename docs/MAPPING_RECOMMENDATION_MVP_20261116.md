# 컬럼 추천 MVP 비교 — 2026-11-16

기준 main `0a60e9238cc0da684a112cb6b32e145c17e8987f`. 현재 PC에서는 **Docker 설치·실행, PostgreSQL 구성·접속, 0009 실제 적용, DB 쓰기/E2E를 모두 금지·보류**한다. 이번 작업은 로컬 합성 자료와 Python 비DB 검사만 수행했다. 모델 다운로드·재실행, 외부 추론/LLM 호출, API 키 요청·저장은 0회다.

## 비교와 실제 결과

기존 [설계](AI_MAPPING_INTEGRATION_DESIGN.md), [벤치마크](DATA_INGESTION_BENCHMARK.md), retriever-eval README/results를 확인하고 정확·별칭 mapper/profile/의미 반증/recommend()를 재사용했다. [새 48건](../contracts/examples/mapping_recommendation_cases_v1.json)은 기존 이름 대조군 4건, 오타·새 표현 28건, 애매함·잘못된 의미·무관한 열 16건이다. 별칭에서 질의를 생성하지 않았고 변형/새 표현 28건이 정확 별칭과 일치하지 않는지도 검사했다. 필드 정의를 아는 작성자의 수작업 합성 셋이며 외부 전문가 블라인드 평가나 실제 기업 정확도 추정은 아니다. 평가 전 예시를 고정했고 기존 cutoff=0.60을 유지했다. 파라미터 탐색·모델 조합·대규모 신규 벤치마크는 하지 않았다.

| 방법 | 정확 Top-1 / 정답 있는 32건 | 잘못된 Top-1 / 전체 48건 | 후보 없음(HOLD) / 48건 | Top-3 / 정답 있는 32건 | ms/열 |
| --- | --- | --- | --- | --- | --- |
| 정확 일치·별칭 후보 | 4/32 = 12.50% | 6/48 = 12.50% | 38/48 = 79.17% | 4/32 = 12.50% | 0.017 |
| SequenceMatcher + 공통 반증 | 25/32 = 78.13% | 6/48 = 12.50% | 17/48 = 35.42% | 26/32 = 81.25% | 0.937 |
| RapidFuzz + 공통 반증 | 25/32 = 78.13% | 6/48 = 12.50% | 17/48 = 35.42% | 26/32 = 81.25% | 0.159 |

**후보 지표이며 자동 적용률/승인 정확도가 아니다.** 약한 별칭·괄호 의미 충돌도 Top-1을 그대로 따른다고 가정해 오추천에 포함한다. 정답 null은 무관하거나 문맥 확인이 필요한 열이다. 후보 HOLD는 후보 없는 컬럼 수이며 실제 파일의 mapping HOLD율이 아니다. 후보가 있어도 필수 매핑 미확인은 기존 파일 HOLD를 유지한다. 예전 16건/43필드·95.35%와 분모가 다르므로 규칙의 성능 저하로 해석하지 않는다.

SequenceMatcher/RapidFuzz는 동일한 최종 의미·프로파일 반증을 사용해 scorer를 비교했다. RapidFuzz는 [공식 ratio](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html#ratio)의 전체 문자열 Indel 유사도다. 부분 문자열 최고점이나 확률이 아니다. Python 3.11.9/RapidFuzz 3.14.6에서 import·입력 파싱 이후 48열을 3회 측정한 중앙값이다. 추천 경로는 profile과 대역 교체 비용도 포함하고 정확 mapper는 profile을 포함하지 않는다. 파일 I/O·HTTP·DB·모델 시간은 제외했다. [수치/실패 목록](MAPPING_RECOMMENDATION_RESULTS_20261116.json)에 평가셋 SHA를 기록했다.

## BGE-M3 연구 재사용

[고정 커밋의 Task A, s0_im](https://github.com/ChungPaMo/retriever-eval/blob/c7f3fce8c81c3365c00cc36295427709c9baa6af/results/trichef_results.json)은 정답 있는 317건에서 Top-1 **94.32%**, Top-3 **99.37%**였다. 임계값으로 선택까지 결정한 전체 test 386건의 오매핑은 **13.73%**였다. RTX 4060 Laptop의 당시 기록은 질의 31.7ms, 묶음 1.33ms/텍스트다. 전체 HOLD율은 이 요약에 없어 계산하지 않았으며 hold_miss_rate와 혼동하지 않는다.

[출처 발췌](../contracts/examples/mapping_bge_research_excerpt.json)는 재실행 없이 보존했다. 후보 집합·질의·하드웨어가 달라 새 48건과 직접 우열을 판정하지 않는다. 이 연구도 별칭을 참고한 합성 셋이라는 한계가 있다. 새 표현의 후보 검색 가능성과 자동 선택 위험이 이미 확인되어 이번에는 모델 실험을 반복하지 않았다.

## 개선 내용과 남은 오류

RapidFuzz는 이 셋에서 SequenceMatcher보다 정확도가 높지는 않았지만 같은 후보 품질로 추천 경로가 약 **5.9배 빨랐다**. 정확/별칭 후보만 쓸 때보다 오타·표기 변형 Top-3 포함률은 12.50%→81.25%다. 서버 별칭의 정규화 결과만 미리 계산하며 업로드 헤더/값은 요청 간 캐시하지 않는다. 별칭 목록은 늘리지 않았다.

기존 정규화가 괄호 안 반품·취소·출고/자재 설명까지 지워 반증이 놓치는 문제도 수정했다. 반증은 괄호 내용을 보존하고, 알려진 역할이 반증되면 유사도만으로 다른 역할을 대신 추천하지 않는다. 초기 비교의 오추천 12/48에서 수정 후 6/48로 줄었다. 이는 같은 평가셋에서 발견·수정한 결과이며 미공개 holdout 개선이라고 주장하지 않는다.

남은 오추천 6건: product_categroy→product_id(정답 product_type은 3순위), 월수요金額→demand_qty, on_hand_value→on_hand_qty, 수량→demand_qty, base_or_available_qty→available_qty, 참고기간→period. 의미·문맥 확인 없이 채택하면 안 된다. calendar_month, 완제품식별번호, 원자재식별번호, item_classificaton, stock_snapshot_date, quantity_per_assembly는 정답이 Top-3에도 없었다. 이 예시들을 별칭에 추가해 점수만 올리지 않았다.

## 권장 MVP와 Upstage 판단

**기존 정확/별칭 + RapidFuzz Top-3 + 값·의미 반증 + 사용자 확인**을 권장한다. RapidFuzz는 오타 후보 검색이며 의미 확정 도구가 아니다. 선택한 열은 기존 column_overrides로 다시 요청하고 검증·승인 게이트를 거친다. 새 표현의 추가 후보가 필요하면 기존 연구에 근거한 로컬 BGE-M3를 다음 단계 선택지로 두되 이번 코드에는 모델 로더/자동 호출을 연결하지 않았다.

Upstage LLM은 **현재 필수 도입으로 확정하지 않는다.** 위와 같은 문맥 모호성이 실제 파일에서 반복되고 규칙·RapidFuzz·BGE 후보로 해결되지 않을 때의 후속 대안이다. 이번 결과만으로 BGE까지 충분하다고 단정하지도 않는다. 현재는 기존 사용자 확인 흐름으로 불확실성을 처리한다.

후속 내부 어댑터 초안(Upstage 공식 API 형식 아님): 입력은 contract_version/entity, 허용 target_fields, 비식별·허용된 열 라벨/열 번호, 값 없는 형식 통계, 로컬 후보/반증/질문이다. 원본 파일·셀 값·개인정보·전체 마스터·파일 경로는 제외하고 외부 전송 승인/필드 allowlist를 먼저 확인한다. 출력은 기존 열 번호별 최대 3개 target enum 후보, 짧은 근거, 확인 질문, requires_user_confirmation=true다. 알 수 없는 열/필드·추가 속성·SQL/코드·DB 쓰기·승인 지시는 거부하고 column_overrides로 자동 적용하지 않는다. 실제 API 클라이언트나 키 설정은 추가하지 않았다.

## 코드와 검증

실제 변경은 recommendation.py의 scorer/반증, RapidFuzz 의존성 고정 3파일, 독립 평가 스크립트·48건 fixture·BGE 발췌·실행 요약, 관련 회귀 테스트와 문서다. 정확 mapper/validator/BatchService/변환/이력 코드는 변경하지 않았다. method=LEXICAL_SIMILARITY와 DTO/API는 유지하고 evidence에 RAPIDFUZZ_RATIO/RANKING_ONLY_NOT_CONFIDENCE를 추가했다. 후보 requires_review=true, persisted=false/auto_approve=false, source SHA/수동 override는 그대로다.

관련 검사 **41 passed**, 최종 전체 비DB pytest **914 passed / 0 failed / 63 skipped**, 21.82초. DB 63개는 접속 차단 상태의 제외이며 통과가 아니다. Starlette/httpx deprecation warning 1건은 기존 것이다. 전체 회귀는 기존 기능 보존을 위한 1회 실행이며 새 성능 실험은 48건에 한정했다. frontend/, modules/file_classifier/, modules/planning_engine/와 migrations/의 diff는 0이며 신규 migration도 없다. pip check는 문제 없음, 저장소 보안 검사 findings=0, 변경 문서 로컬 링크 48개 정상, Git whitespace 검사 통과다.

재현: `.venv/Scripts/python.exe -X utf8 scripts/evaluate_mapping_recommendations.py`. 합성 48건만 읽고 상세 결과는 ignored .artifacts에 기록한다. `--summary-output docs/MAPPING_RECOMMENDATION_RESULTS_20261116.json`을 명시하면 검토용 요약도 갱신한다.

## 기존 개발 PC에서 진행할 DB 작업

1. 실제 Docker/PostgreSQL 서버·컨테이너/볼륨·DB/역할·데이터셋과 독립 회귀 DB의 격리를 확인하고 기존 승인 배치/예측 이력을 읽기 전용으로 기록한다.
2. 보존 조건·절차를 검토한 뒤 기존 0009를 모든 등록 스키마(보관 상태 포함)에 적용하고 0001~0008/기존 데이터 보존을 확인한다.
3. 독립 회귀 DB에서 원본/manifest/출력 바이트 원자 저장·실패 롤백·불변 트리거·동시 입력 재사용·데이터셋 격리/신규 스키마 v2를 검증한다.
4. 승인 전 배치→재검증→명시적 승인→월수요/예측 입력과 실DB E2E를 검증하고 개발 데이터 사전/사후 상태를 대조한다.
5. 기존 회귀 fixture는 초기화/DROP/TRUNCATE를 포함하므로 대상 식별과 해당 실행의 별도 승인 이후에만 사용한다. 개발 DB/chungpamo_test를 초기화하거나 현재 PC에서 대체 실행하지 않는다.
