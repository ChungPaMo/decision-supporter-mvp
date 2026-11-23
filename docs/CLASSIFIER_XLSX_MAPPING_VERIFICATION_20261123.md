# 현실형 XLSX 분류·컬럼 추천 검증

2026-11-23 KST, 보조 PC. 시작 `main`은 [`b2b3ecd`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/b2b3ecd7941b2e6b3cc706d95614d09a584f0115)다. 이번 작업은 이훤의 [분류 연동 요청](../modules/file_classifier/CONTRACT_REQUESTS.md) 중 백엔드 등록 경로와 HOLD 계약을 구현하고, 같은 폴더의 합성 Excel 원본으로 업로드 파서와 컬럼 추천을 확인했다.

## 자료와 재현

`samples/inbox/`의 추적 XLSX 200개와 `labels.json`을 재사용했다. 라벨의 SHA-256은 `79606e15799b6cb41149d2df384d75e0d98856b3a9795d6702f77018c2c237ad`다. 생성기의 메모리 `build()` 결과를 라벨과 대조하고 선언된 표 헤더의 원본 위치를 확인했다. 파일 재생성 및 저장은 하지 않았으며 200개 파일과 라벨의 전후 SHA를 대조했다. 아래 명령은 Git 제외 `.artifacts/classifier_xlsx_evaluation.json`에 파일별 SHA, 시트, 실제 표 헤더와 파서가 쓴 행, 병합·숨김·수식·빈 행·제목, API 응답 요약을 저장한다. [평가 스크립트](../scripts/evaluate_classifier_xlsx.py)

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_classifier_xlsx.py
```

## 파서와 분류 결과

| 검사 | 실제 결과 |
| --- | --- |
| XLSX 입력·시트 | 200개 모두 파싱 가능. 보이는 시트 358개, 여러 보이는 시트가 있는 파일 98개, 숨긴 시트 6개 제외 |
| 실제 표 헤더 | 주 시트 첫 정답 헤더가 1행 이후에 있는 파일 190개. 파서가 첫 정답 헤더를 포함한 파일은 **18/200**. 원본에는 표 블록 422개, 여러 블록이 있는 파일 47개 |
| 병합과 제목 | 병합이 있는 시트 97개, 파서가 2행 헤더로 만든 시트 97개. 생성기가 `title`로 넣은 행을 헤더에 포함한 시트도 97개 |
| 숨긴 열, 수식, 빈 행 | 숨긴 열 14개는 열 위치를 유지한 채 파서에 포함. 본문 수식 89셀 모두 캐시가 없어 빈 값으로 읽힘. 원본 빈 행 866개 중 본문에 남은 빈 행 0개 |
| 문서 종류 규칙 `doctype-0.3.0` | 라벨과 dev **91/91**, test **109/109** 일치, HOLD 0, 오분류 0. 이 corpus의 라벨과 비교한 결과이며 다른 기업 XLSX로 일반화하지 않는다 |
| 업로드 `/classifications/file` 기본 헤더만 전달 | 200개 모두 `HOLD / UNKNOWN`, 표준 추천 0. 문서 종류 규칙과 다른 입력·분류 체계다 |

등록 API 지원은 표준 제품·자재·BOM·재고·월 수요와 별도 `capacity`·`routing` 양식이다. 이 200개 원본에서는 표준 등록 전체를 구성하는 입력을 확인하지 못했다. 템플릿 내용 기준으로 162개는 비대상 문서/보고서, BOM 반복·다단 블록 16개는 재구조화 대상, 판매 3개는 변환 정책·필수 거래 키 확인 대상, 재고 보고 7개는 기준일·보유/할당 재고 의미 확인 대상, 혼합 품목 마스터 3개는 제품·자재 구분 대상이다. 나머지 9개는 평면 BOM의 세 열 역할을 직접 해석할 수 있지만 BOM 번호·버전·유효 시작일·구성 유형·단위 등 필수 항목이 빠져 있다. RCCP/CRP 부하 보고서는 승인 CAPA 시간예산으로 사용하지 않았다.

## 컬럼 추천 결과

평면 BOM 9개에만 `/ingest/mapping-suggestions`를 `entity=bom`으로 호출했다. 골드는 템플릿의 `Upper-part-id`→`product_id`, `Lower-part-id`→`component_id`, `Quantity`→`qty_per` 세 열이다. 원본 파일과 실제 표 사각형만 복사한 메모리 XLSX를 각각 검사했다. 복사본에 필드명·누락값·단위·생성 행을 더하지 않았다.

| 입력 | Top-1 | Top-3 | 오추천 Top-1 | 잘못된 하위 후보 | 후보 없음 | 파일 HOLD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 원본 평면 BOM | 0/27 | 0/27 | 0 | 0 | 27 | 9/9 |
| 표 범위만 복사, 최종 코드 | 9/27 | 9/27 | 0 | 0 | 18 | 9/9 |

원본에서 첫 `Structure` 행을 헤더로 읽었다. 예를 들어 `최종 (99).xlsx`의 실제 헤더는 3행, 파서 헤더는 1행이다. 표만 분리하면 `Quantity`가 `qty_per`로 검색됐지만 상·하위 품목 두 열은 후보가 없었다. 처음 측정에서는 9개 모두 `Quantity`에 `unit`이 두 번째 후보로 붙었다. 비어 있지 않은 값이 모두 숫자인 열은 `unit`/`base_unit`에서 제외하도록 추천에 `NUMERIC_VALUES_ARE_NOT_UNITS` 반증을 추가했다. 최종 실행에서 이 잘못된 하위 후보 9건이 사라졌으며, 올바른 `EA`/`kg` 열과 수량 후보를 유지하는 API 회귀를 추가했다. 정확 매퍼와 저장 검증을 수정하지 않았다.

11/22 평가셋은 **합성 헤더 48개**였다. 당시 RapidFuzz Top-1 25/32, Top-3 26/32, 잘못된 Top-1 3/48, 후보 HOLD 20/48이었다. BGE-M3 보완은 31/32, 32/32, 7/48, 10/48이었고 이전 적용 기준을 충족하지 못했다. 여기의 27열과 분모·범위가 다르며 기존 48개 성능을 새로 측정하거나 모델을 다시 실행하지 않았다. [기존 평가](MAPPING_BGE_EVALUATION_20261122.md)

## 분류 API 계약과 담당자 인계

- `POST /classifications`, `POST /classifications/file`, `POST /ingest/classified-mapping`의 `classification` 결과에 `hold_kind`와 `registration_hint`를 선택 필드로 추가했다. 기존 `hold`, 다섯 `recommended_entity`, `candidates`, 사람이 읽는 `reasons`를 유지한다. 비HOLD에서 `hold_kind`는 `null`이다.
- `NEEDS_TRANSFORM`은 변환 가능성 안내, `OTHER_ROUTE`는 별도 등록 경로, `AMBIGUOUS`는 분리·수동 확인, `UNKNOWN`은 근거 부족이다. 변환 가능성은 기존 합성 판매 정책과 실제 열 확인을 거친다. 가로 월 수요나 임의 판매 원장을 현 정책에 자동 전달하지 않는다.
- `registration_hint={"entity":"capacity","sections":["hours_budgets","quantity_limits","resources"]}`처럼 실제 `/batches` 등록 엔터티와 양식 섹션을 돌려준다. Routing은 `{"entity":"routing","sections":["routing_steps"]}`다. 기존 DTO의 필수·허용 헤더를 모두 만족하는 양식에서 힌트를 만들며, 중복 헤더, 다른 시트, CAPA/Routing 혼합을 보수적으로 보류한다. `hold=true`, `hold_kind=OTHER_ROUTE`, 다섯 유형의 `recommended_entity=null`을 유지한다. 값, 승인 참조, 단위, 정책은 별도 기존 등록 검증을 거친다.
- 이훤에게는 `ClassificationOutput.hold_kind`를 분류 결과에서 직접 제공하도록 인계한다. 현재 이전 모듈 `rules-0.3.0`에 한해 인식 가능한 근거 문구를 임시 변환하며, 모듈이 직접 제공하는 구조화 코드도 받는다. CAPA·Routing 평가에서 `capacity`/`routing`과 네 섹션 이름을 사용한다. 문서 종류 API와 임베딩 연결은 별도 검토 대상이다.
- 나미님은 `hold_kind`로 안내 문구를 선택하고 `registration_hint`가 있을 때만 해당 별도 등록 경로에 대한 명시적 안내를 표시한다. 기존 `reasons`는 설명으로 남긴다. `NEEDS_TRANSFORM`이어도 사용자 확인을 받으며, 다른 사유의 공통 `transform_preview_url`은 변환 권유로 해석하지 않는다. 기본 `/ingest/classified-mapping`은 단독 힌트에서 `selected_entity=null`, `mapping=null`, `persisted=false`, `auto_approve=false`를 반환한다.

실제 기업형 입력 확대에는 사용자가 확인한 헤더/표 범위와 다중 블록 처리 계약이 남아 있다. 제목 자동 건너뛰기나 숨긴 열 제거를 공용 파서에 일괄 적용하면 기존 배치의 행 위치와 해석이 바뀔 수 있어 이번에는 현행 동작을 측정했다. [OpenAPI](../contracts/openapi.json) · [모듈 Schema](../contracts/schemas/module_interfaces_draft.json)

## 비DB 검증

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest --no-db -q -k 'not (test_columns_match_models or test_status_check_matches_enum or test_gate_objects_are_generated or test_entity_check_matches_supported_entities)'
```

최종 **1,115 passed / 0 failed / 66 skipped / 6 deselected**, 18.44초. 66개는 DB 접속 차단으로 건너뛰었고 6개는 오프라인 Alembic 명령 호출을 피하기 위해 선택 제외했다. 기존 Starlette/httpx 경고 1건이 있다. 신규·기존 분류, 양식 라우팅, 읽기 전용 매핑, OpenAPI/JSON Schema 동기화와 공식 합성 입력 E2E가 통과했다. 첫 전체 실행에서 잘못된 하위 후보의 존재에 의존했던 기존 assertion 1건이 실패했다. 두 열의 `demand_qty` 후보와 `AMBIGUOUS_COLUMNS` HOLD를 직접 대조하게 바꾸고 잘못된 수동 선택·검증·승인 차단 검사를 유지했다. Docker·DB 접속·마이그레이션·DB 테스트와 모델 다운로드·외부 LLM은 미실행이다.

`scripts/security_check.py`의 전체 트리 검사에서는 기존 추적 합성 XLSX 200개와 생성기의 전화 형식 문자열 1건을 보고했다. 이번 변경 파일에 해당하는 발견은 0건이며 보안 검사 예외 규칙은 추가하지 않았다.
