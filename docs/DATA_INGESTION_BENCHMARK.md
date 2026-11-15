# 데이터 입력 벤치마크 및 1차 검증 결과

2026-11-15. 기준 SHA `ff448ace16aa58d4fb963bac6ab52841966b72fa`. 새 구현의 최종 SHA는 Git 이력/완료 보고를 따른다. 모든 데이터는 합성이고 외부 AI 호출은 0회다. [연구 결과](AI_ASSISTED_DATA_INGESTION_RESEARCH.md)와 이 문서의 자체 측정을 섞지 않는다.

## 정답·재현 방법

- [수작업 gold 16건](../contracts/examples/ingestion_benchmark_cases.json): 헤더 순서, 별칭, typo, 복수 수량, 금액/수량, 주문/출고, 반품/정상, 제품/자재, 허용 월 형식, 숫자/단위 오류, 동일/충돌 중복, 수동 override, 값/마스터 지원 코드 후보를 명시했다. 정답은 사람이 정했고 시스템 추천을 정답으로 재사용하지 않았다.
- 생성기 `modules/planning_engine/synthetic/generate.py`는 읽기 전용이다. `runpy`로 실행한 함수의 OUT만 별도 임시 경로로 지정하여 새 원본/표준/오류 fixture를 만든다. 소유 폴더에 생성물을 쓰지 않는다.
- 판매 변환은 백엔드 독립 구현이며 생성기의 aggregate_sales/convert 함수를 변환기로 호출하지 않는다. 생성기 정답 `upload/05_monthly_demand.csv`와 제품·월·Decimal 수량·단위를 정렬 대조한다. 키 중복·누락·수량 차이를 허용하지 않는다.
- `scripts/benchmark_ingestion.py`가 실행시간·Python 할당 peak 및 결과 요약을 Git 제외 `.artifacts/ingestion_benchmark.json`에 기록한다. 표준 CSV도 `.artifacts/ingestion_monthly_demand.csv`에만 둔다. 원본 행/JUnit/로컬 경로는 Commit하지 않는다.

```powershell
./.venv/Scripts/python.exe -X utf8 scripts/benchmark_ingestion.py
# 기존 무시된 합성 자료를 변경 없이 읽을 때만:
./.venv/Scripts/python.exe -X utf8 scripts/benchmark_ingestion.py --existing-synthetic
```

## 별칭 baseline과 보조 경로 비교

동일한 16건을 기존 map_sheet+run_preview와 새 recommend+동일 validator로 검사했다. gold mapping의 null은 안전한 원본 열이 없음을 뜻한다. 이 테스트의 표본 크기는 일반 기업 파일 정확도를 추정하기에 충분하지 않다.

| 지표/분모 | 기존 별칭 | 새 보조 경로 |
| --- | --- | --- |
| 필수 의미가 명확한 field-column 43개의 선택 일치율 | 41/43 = **95.35%** | 41/43 = **95.35%** (existing_mapping 보존) |
| 같은 43개 정답의 후보 포함률 | 기존 선택만 41/43 = **95.35%** | top-3 42/43 = **97.67%** |
| 잘못된 자동 선택 field 수 | **0** | **0** |
| mapping HOLD 파일/16 | 7/16 = **43.75%** | 8/16 = **50.00%** |
| 검토·선택 필요 field proxy | **7** | **8** |
| 부적합/HOLD gold 10건의 통과율 | **0/10** | **0/10** |
| 정상 gold 6건의 잘못된 거부율 | **0/6** | **0/6** |

‘선택 일치’는 파일 통과 여부와 별개로 기존 canonical/alias 선택 위치를 비교한다. 새 경로는 fuzzy를 자동 적용하지 않아 이 값이 늘지 않는다. top-3는 검토 후보 recall이며 승인/자동 매핑 정확도가 아니다. qty 데이터가 숫자가 아닌 경우 반증으로 후보를 막으므로 일부 semantic gold는 후보에서 빠질 수 있다. 후보를 더 낸다는 이유로 모두 수용하지 않는다.

HOLD가 늘어난 1건은 숫자 필드의 자료형 반증이다. proxy는 필수 field 중 없음/복수/명시적 확인·반증으로 검토가 필요한 수를 센 것이며 실제 사람의 검토 시간/수정 횟수를 측정한 값은 아니다. bad/normal 통과율은 기존 validator 결과와 HOLD 게이트의 결합이며 사람이 확인한 fuzzy를 적용했을 때의 미래 성능을 뜻하지 않는다. 기존 수동 override 우선순위와 월 수요 중복 정책을 바꾸지 않았다.

## 실제 합성 판매 원본 대조

현재 생성기는 통합 파일 하나가 아닌 **2022~2026 연도별 5개 CSV**를 만든다. 합계 크기 **13,299,665 bytes**다. 실제 데이터를 다시 생성하여 다음을 확인했다.

| 항목 | 결과 |
| --- | --- |
| 원본 행 수 | **86,214** |
| 정상 거래 포함 | **83,984** |
| 취소 거래 제외 | **887** |
| 반품 별도 처리 | **1,343** |
| 원본/집계 오류 | **0 / 0** |
| 최종 월별 수요 | **498행** |
| 정상 원본 수량 / 월별 합계 | **1,812,610 / 1,812,610 EA** |
| 제외 취소 수량 | **11,240** |
| 별도 반품 수량 | **8,670**; 정상 수요에서 차감하지 않음 |
| 제품·월·수량·단위 정답 일치율 | **498/498 = 100%** |
| 정상 수량 보존율 | **100%** |

정책은 `CHUNGPAMO_SYNTHETIC_SALES` v1.0, 주문일자·정상만 포함·팩=EA factor1·반품 별도·거래 키 중복 오류다. 합성 회사에 한정하며 다른 기업에 자동 적용하지 않는다. 연도별 SHA 5개와 policy/input/result digest를 결과에 남긴다. API는 5파일 multipart 및 preview 결과까지 대조하는 회귀 테스트로도 검증한다.

## 표준 업로드와 errors/ 검증

기존 승인 gate를 사용하는 **명시적 인메모리 테스트 저장소**로 표준 업로드 9종을 모두 검증했다. PostgreSQL 검증은 아래 별도 항목이다. 오류 폴더 이름만 보고 모두 거부해야 한다고 가정하지 않는다.

| 오류 폴더 fixture | gold 및 실제 결과 |
| --- | --- |
| bom_unknown_material.csv | HAS_ERRORS |
| demand_missing_qty.csv | HAS_ERRORS |
| inventory_negative_qty.csv | HAS_ERRORS |
| products_unknown_unit.csv | HAS_ERRORS |
| demand_bad_period_format.csv (`YYYY/MM`) | **READY_FOR_APPROVAL** — 기존 허용 형식 |
| demand_duplicate_period.csv (동일 수량) | **READY_FOR_APPROVAL** — 경고 후 중복 제거 |
| sales_orders_dirty_sample.csv | **HAS_ERRORS**, 원본 205 / 정상 유효 134 / 오류 71 / 부분 집계 9행 |

dirty 판매의 날짜 점 구분·지역식 날짜·단위 문자가 붙은 수량·빈 코드/수량·중복 거래 등을 자동 추정하지 않는다. 부분 집계 9행은 완성된 정상 결과가 아니며 등록용 성공으로 취급하지 않는다. 이 오류 fixture에서 보존율 100%라고 주장하지 않는다.

## 시간·메모리 측정 범위

2026-11-15 로컬 1회 재생성 benchmark 실행에서 transform 시간 **16.981초**, `tracemalloc` Python peak **20,220,157 bytes (약 19.28 MiB)**였다. 측정은 파일 bytes를 읽은 **이후 transform 함수에 한정**한다. 입력 13.30 MB/ASGI·multipart·파서·프로세스 RSS·생성기·후속 fixture 검증 메모리를 포함하지 않는다. tracing 자체의 CPU overhead를 포함한 단일 실행이며 성능 SLA나 전체 서버 메모리 상한으로 해석하지 않는다. 같은 하드웨어라도 실행시간은 달라진다.

CSV 변환은 raw row 목록 전체를 만들지 않는다. 입력 파일 바이트, 제한된 거래 키 set/날짜 cache, aggregate 및 각 그룹 trace 최대5개를 보관한다. 전체 요청/파일/행/컬럼/그룹 수에는 [설계 문서의 한도](AI_MAPPING_INTEGRATION_DESIGN.md)가 있다. XLSX profile은 기존 parser를 제한된 크기에서 사용한다.

## 실행한 회귀 검증

| 실행 | 결과 |
| --- | --- |
| 새 단위/생성기 테스트 | 초기 **28 passed**; 이후 전체 회귀에 포함 |
| PostgreSQL 포함 전체 pytest | **638 passed / 0 failed / 0 skipped**, 기존 DB 55개도 실행 |
| 최종 비DB 전체 pytest | **577 passed / 0 failed / 61 skipped**; 기존/추가 DB 테스트는 접속 차단 모드의 skip이며 통과가 아님 |
| DB 대상 | 127.0.0.1:55433/chungpamo_regression, chungpamo_regression_runner |
| 추가 DB 검증 | 승인 마스터의 CP/Legacy scope, 교차 제품 차단, 미확인 정책 상태, 새 API의 배치 무생성 |
| 개발 DB 강제 읽기 전용 | 새 API 2개 + 기존 데이터셋 API 9개 그룹 통과, 최종 회귀 종료 후에도 기존 업무 56개 테이블 행 수/hash 동일 |
| OpenAPI/JSON Schema | 생성 스크립트 갱신 + 동기화 테스트 |
| TypeScript/Vite build/E2E TypeScript | 모두 통과; frontend 소유 파일 변경 없음 |
| Python 컴파일/pip check/보안 | 통과; 공개 후보의 known-secret/금지 파일·경로 검사 탐지 0건 |

기존 OpenAPI path의 request/response 정의는 모두 동일하다. 기존 schema 중 바뀐 것은 새 오류 6개를 추가한 ErrorCode뿐이고, 새 API 3개와 schema 모델 20개가 추가됐다. 마스터/data_contract 및 기존 forecast/planning schema를 변경하지 않았다.

중간 비DB 전체 실행에서 신규 API의 snapshot/가이드 미갱신 **2건이 실패**했다. OpenAPI 생성기와 가이드 경로/오류 목록을 갱신했고 이후 전체 DB 회귀에서 통과했다. 테스트를 삭제/완화/skip 전환하지 않았다. 기존 Starlette/httpx deprecation warning 1건은 남는다.

이번 작업에 한정한 사용자 재승인 후 실제 DB/user, 허용 스키마, sentinel, SYNTHETIC 출처를 검사하고 회귀 DB 안의 public/CP 테스트 스키마·과거 history 스키마만 초기화했다. 개발 `chungpamo`, 기존 `chungpamo_test`, 55432 및 다른 프로젝트 자원을 초기화/수정하지 않았다. 회귀 DB는 삭제하지 않고 보존한다. 기존 migration 0001~0008 및 owner 폴더도 수정하지 않았다.

기존 [DB 검증 문서](DB_REGRESSION_E2E_VERIFICATION.md)의 608개는 이전 단계 기록이다. 이 문서의 새 실행 결과와 구분한다. 원본 pytest XML, 벤치마크 JSON, generated CSV, 읽기 전용 fingerprint는 Git 제외 `.artifacts`에만 보관한다.

## 후속 측정과 미실행

외부 AI/embedding의 매핑 성능·비용·지연은 **미측정**이다. 실제 기업 파일의 정답·개인정보 정책을 합의한 후 같은 gold 구조로 평가한다. 매핑 규칙의 영구 저장, full lineage paging, 원본→변환→배치의 영구 provenance는 미구현이다. 데이터셋 선택/정책 확인 frontend는 정마나미 담당이며 이번에 구현·브라우저 실행하지 않았다. 계획/What-if 계산·정식 승인 501은 유지한다.

후속 변경 요청은 [팀별 경계 및 입력 보조 계약](AI_MAPPING_INTEGRATION_DESIGN.md)을 따른다. 의미가 다른 컬럼을 정상 통과시키는 오류를 최우선 지표로 유지하고, 추천 recall만으로 승인을 자동화하지 않는다.
