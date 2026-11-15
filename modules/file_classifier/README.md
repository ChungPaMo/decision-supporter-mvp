# File classifier · 이훤

`file_classifier.classify(ClassificationInput) -> ClassificationOutput`. 업로드 파일의 열 이름을 보고 자료 유형을 추천하거나 보류한다. 규칙 기반이며(`rules-0.2.0`) 외부 서비스·DB·원본 파일을 쓰지 않는다. 추천은 사용자 확인용 제안이고 승인 단계를 대신하지 않는다.

입력은 파일 정보·SHA256·시트명·컬럼·허용한 최대 20개 샘플 행이다. /classifications(JSON)와 /classifications/file(multipart)는 같은 classify 함수를 사용한다. 공유 DTO는 contracts/interfaces/modules.py다. 공통 API·DB 저장·승인 gate를 이 모듈에서 수정하지 않는다. 경계 변경은 김대영에게 계약 변경을 요청한다.

## 판단 방식 (`src/file_classifier/rules.py`)

1. 열 이름을 정규화한다(소문자, 공백·괄호·기호 제거). 첫 행이 열 이름이 아니면 샘플 행 앞쪽 5줄에서 열 이름 줄을 찾는다.
2. 다섯 유형(product, material, bom, inventory, monthly_demand)마다 유형을 특정하는 핵심 열 조합이 있는지 본다.
3. 핵심 조합이 있고, 아는 열의 비율이 기준 이상(제품·자재 70%, 그 외 60%)이며, 2순위와 0.15 이상 차이 날 때만 추천한다.
4. 표가 있는 시트가 모두 같은 유형일 때만 파일 전체를 추천한다. 유형이 섞여 있으면 보류한다.

보류하는 경우: 품목 코드·이름만 있어 제품/자재를 구분할 수 없음, 모르는 열이 많은 보고서, capacity·routing, 열 이름이 없는 파일, 유형이 섞인 통합 문서. 판매·출고 내역과 월이 가로로 펼쳐진 표는 보류하되 monthly_demand로 변환할 수 있다고 안내한다(후보에 monthly_demand 포함).

점수는 "아는 열의 비율"이며 확률이 아니다. 파일명은 판단에 쓰지 않는다. 기준값(0.6/0.7/0.15)은 담당자가 합성 시험셋으로 정한 값이고 팀 합의가 필요하다.

## 측정 결과 (2026-11-16, 합성 자료)

```powershell
./.venv/Scripts/python.exe -m pytest modules/file_classifier -q
python -X utf8 modules/file_classifier/tests/fixtures/evaluate.py --failures
```

| 대상 | 건수 | 올바른 추천·보류 | 오분류 | 추천해야 하는데 보류 |
|---|---|---|---|---|
| 자체 시험셋 (dev 105 / test 158) | 263 | 263 | 0 | 0 |
| 백엔드 매핑 별칭으로 만든 열 조합, 규칙 수정 전 (rules-0.1.0) | 2,500 | 1,543 | 22 | 935 |
| 같은 열 조합, 규칙 수정 후 (rules-0.2.0) | 2,500 | 2,450 | 0 | 50 |

응답시간은 사례당 중앙값 0.1ms 안팎, 최대 1.2ms 미만이다(개발 PC, 분류 함수만, 실행마다 조금 다르다).

읽을 때 주의할 점:
- 자체 시험셋은 규칙과 같은 사람이 같은 어휘로 만들었다. 전부 맞는 것은 당연하며 실제 성능의 근거가 아니다.
- 백엔드 별칭 조합은 `backend/app/ingest/mapping.py`의 강한 별칭으로 유형마다 500건씩 열 이름만 조합한 것이다. 수정 전 결과가 처음 보는 어휘에 대한 실제 수준에 가깝다. 수정 후 결과는 그 별칭을 규칙에 반영한 뒤라 독립 측정이 아니다.
- 수정 전 오분류 22건은 모두 월 수요를 제품 마스터로 추천한 것이다(기간·수량 열 이름을 몰랐음). 모르는 열 이름에 기간·수량을 뜻하는 말이 있으면 마스터로 추천하지 않도록 고쳤고, 열 이름을 임의로 바꿔도 다른 유형으로 추천하지 않는지 시험한다.
- 남은 보류 50건은 `품목코드, 품목명, 단위`처럼 제품인지 자재인지 열 이름으로 알 수 없는 조합이다.
- 실제 기업 파일, 다른 사람이 만든 시험 파일로는 측정하지 않았다.

## 시험셋 (SYNTHETIC)

`tests/fixtures/build_cases.py`가 가상 회사(㈜충파모제지 설정 참고) 기준의 분류 시험 사례를 만든다. 표준 라이브러리만 쓰며 같은 SEED면 결과가 같다.

```powershell
python -X utf8 modules/file_classifier/tests/fixtures/build_cases.py
```

- `tests/fixtures/cases.json`: 사례별 분류 입력(payload)과 기대 결과. `tests/fixtures/manifest.csv`: 사례 목록.
- 기대 결과: `expected_entity`(올바른 추천, 없으면 null), `must_hold`(보류만 정답), `hold_ok`(보류해도 오분류로 보지 않음), `guidance_entity`(보류하되 변환 대상 entity를 안내).
- 정한 규칙(2026-11-16): capacity/routing은 분류 범주에 넣지 않고 보류한다. 판매 주문 원장·가로로 펼친 월별 표처럼 변환이 필요한 자료는 보류하고 monthly_demand로 안내한다.
- `test_fixture_cases.py`는 시험셋이 입력 계약을 지키는지 확인하고, `test_classifier_rules.py`는 사례별 기대 결과와 열 이름 변형에 대한 안전성을 확인한다.
