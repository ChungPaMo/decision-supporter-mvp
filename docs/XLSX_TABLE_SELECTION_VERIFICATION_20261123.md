# XLSX 표 선택 비DB 검증

2026-11-23 KST, 보조 PC. 시작 `main`은 [`5002853`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/50028536a4af176306704be574409b142f10eaaf)다. 기존 합성 XLSX 200개와 라벨을 재사용했다. [이전 검증](CLASSIFIER_XLSX_MAPPING_VERIFICATION_20261123.md)

| 검증 | 기본 파싱 | 실제 좌표 지정 |
| --- | --- | --- |
| 같은 원본 200개에서 첫 표 헤더 확인 | 18/200 | 200/200 |
| 평면 BOM 9개의 정답 27열 Top-1 | 0/27 | 9/27 |
| 평면 BOM Top-3 | 0/27 | 9/27 |
| 평면 BOM 오추천 Top-1 / 하위 후보 | 0 / 0 | 0 / 0 |
| 평면 BOM 추천 없음 | 27/27 | 18/27 |
| 평면 BOM 파일 HOLD | 9/9 | 9/9 |

생성기가 선언한 표 헤더를 원본 시트에서 먼저 찾아 선택 좌표를 고정했다. 선택형 `/ingest/profile`이 200개 모두에서 해당 헤더·원본 열·시트·SHA를 돌려주는지 대조했다. 이 수치는 파일에서 헤더를 자동으로 찾는 정확도가 아니다. 라벨의 문서 종류 규칙 결과는 별도이며 기존 200/200과 같았다. 계획·재고 보고서 등 표준 입력에 해당하지 않는 파일은 구조만 검사했다.

평면 BOM에는 `/ingest/mapping-suggestions`로 원본과 범위만 전달했다. `Structure` 제목을 건너뛰어 `Quantity`의 `qty_per` 후보 9개를 확인했다. 이전의 표 복사본 Top-1·Top-3 9/27과 같다. `Upper-part-id`, `Lower-part-id` 18열은 후보가 없고 BOM ID, 버전, 구성 유형, 단위 등 필수 입력도 빠져 있다. 선택은 해당 위치의 읽기를 바꾸며 누락된 의미나 데이터를 만들지 않는다.

TestClient 회귀는 숨긴 시트 거부, 숨긴 열 위치 보존, 병합 영역 표시·거부, 수식 캐시 없음과 빈 행, 중복 헤더, SHA 불일치, 잘못된/중복 선택, 필수 컬럼 HOLD를 확인했다. 동일 파일에서 다른 시트·표로 변경해도 SHA는 동일하고 선택 좌표 및 집계 대상은 바뀐다. 변환에서는 C~I를 선택한 경우에도 누락 수량을 실제 8행 E열(5)로 보고했다. 같은 원본에서 마지막 행만 다르게 지정해도 변환 입력 지문이 달라졌다. 저장·승인은 기존 경로를 사용한다. [나미님 UI 인계](XLSX_TABLE_SELECTION_HANDOFF.md)

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_classifier_xlsx.py --output .artifacts/classifier_xlsx_range_evaluation.json
.\.venv\Scripts\python.exe -X utf8 -m pytest --no-db -q -k 'not (test_columns_match_models or test_status_check_matches_enum or test_gate_objects_are_generated or test_entity_check_matches_supported_entities)'
```

최종 비DB pytest **1,128 passed / 0 failed / 66 skipped / 6 deselected**. 66개 실DB 검사를 접속 차단으로 건너뛰었고 Alembic 명령을 호출하는 오프라인 검사 6개를 선택 제외했다. 기존 Starlette/httpx 경고 1건이 남았다. 기존 RapidFuzz 48건의 고정 데이터와 결과 정합성 회귀, 공식 합성 입력과 기존 변환 이력 회귀, OpenAPI/Schema 동기화가 통과했다. 모델 다운로드·재평가, Docker·PostgreSQL 접속·마이그레이션, 프론트엔드 브라우저는 미실행이다.

전체 트리 보안 검사는 기존 합성 XLSX 200개와 분류기 생성기의 전화 형식 문자열 1건을 보고했다. 변경 파일 발견은 0건이다. 원본과 라벨 201개 SHA를 작업 전후 대조했다. 상세 파일별 결과는 Git 제외 `.artifacts`에 쓴다.
