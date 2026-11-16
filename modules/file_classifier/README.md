# File classifier · 이훤

업로드된 엑셀·CSV가 어떤 자료인지 판단하는 모듈이다. 두 가지 기능이 있고 둘 다 규칙 기반이다. 외부 서비스·DB를 쓰지 않고 원본 파일은 읽기만 한다. 결과는 사용자 확인용 제안이며 승인 단계를 대신하지 않는다.

| 기능 | 질문 | 범주 | 진입점 |
|---|---|---|---|
| 테이블 분류 | 이 파일을 어느 테이블에 등록할까 | product, material, bom, inventory, monthly_demand, 또는 보류 | `file_classifier.classify()` → `/classifications`, `/classifications/file` |
| 문서 종류 분류 | 이 파일은 어떤 업무 문서인가 | BOM, MPS, MRP, RCCP, CRP, MES, ERP, 미분류, 또는 확인 필요 | `file_classifier.doctype.classify_workbook()` → `tools/sort_folder.py` |

공통 API·DB 저장·승인 gate·공유 DTO(`contracts/interfaces/modules.py`)는 이 모듈에서 수정하지 않는다. 경계 변경은 김대영에게 계약 변경을 요청한다.

## 빠른 사용법

```powershell
# 시험
./.venv/Scripts/python.exe -m pytest modules/file_classifier -q

# 테이블 분류 채점
python -X utf8 modules/file_classifier/tests/fixtures/evaluate.py --failures

# 문서 종류 분류: 더미 엑셀 200개 만들기 → 폴더 일괄 분류
python -X utf8 modules/file_classifier/samples/make_samples.py
python -X utf8 modules/file_classifier/tools/sort_folder.py modules/file_classifier/samples/inbox --labels modules/file_classifier/samples/labels.json --out modules/file_classifier/samples/분류결과.xlsx
```

`sort_folder.py`는 어떤 폴더든 넣을 수 있다(`--labels`는 채점할 때만). `.xlsx`와 `.csv`는 저장소 `.gitignore` 대상이라 더미 파일·결과 파일·`manifest.csv`는 올라가지 않는다. 생성기와 정답(`labels.json`, `cases.json`)만 저장소에 있다. 더미 생성과 폴더 분류에는 openpyxl이 필요하다.

## 구성

| 경로 | 내용 |
|---|---|
| `src/file_classifier/__init__.py` | `classify()` 진입점, `AVAILABLE = True` |
| `src/file_classifier/rules.py` | 테이블 분류 규칙 (`rules-0.2.0`) |
| `src/file_classifier/doctype.py` | 문서 종류 분류 규칙 (`doctype-0.3.0`) |
| `tools/sort_folder.py` | 폴더를 읽어 결과 엑셀(분류결과, 요약, 채점 시트)을 만든다 |
| `samples/make_samples.py`, `samples/labels.json` | 문서 종류 분류용 실제 `.xlsx` 더미 200개 생성기와 정답 |
| `tests/fixtures/build_cases.py`, `cases.json`, `evaluate.py` | 테이블 분류용 시험 사례 263건 생성기, 정답, 채점 |
| `tests/` | 경계, 사례별 기대 결과, 열 이름 변형 안전성, 문서 종류 규칙 시험 |

---

## 1. 테이블 분류 (`rules.py`)

### 판단 방식

1. 열 이름을 정규화한다(소문자, 공백·괄호·기호 제거). 첫 행이 열 이름이 아니면 샘플 행 앞쪽 5줄에서 열 이름 줄을 찾는다.
2. 다섯 유형마다 그 유형을 특정하는 핵심 열 조합이 있는지 본다.
3. 핵심 조합이 있고, 아는 열의 비율이 기준 이상(제품·자재 70%, 그 외 60%)이며, 2순위와 0.15 이상 차이 날 때만 추천한다.
4. 표가 있는 시트가 모두 같은 유형일 때만 파일 전체를 추천한다.

보류하는 경우: 품목 코드·이름만 있어 제품/자재를 구분할 수 없음, 모르는 열이 많은 보고서, capacity·routing, 열 이름이 없는 파일, 유형이 섞인 통합 문서. 판매·출고 내역과 월이 가로로 펼쳐진 표는 보류하되 monthly_demand로 변환할 수 있다고 안내한다.

점수는 "아는 열의 비율"이며 확률이 아니다. 파일명은 판단에 쓰지 않는다. 입력은 파일 정보·시트명·컬럼·허용한 최대 20개 샘플 행뿐이다(샘플 행 기본값 0).

### 시험 사례 263건 (SYNTHETIC)

`tests/fixtures/build_cases.py`가 가상 회사 기준으로 만든다. 같은 SEED면 결과가 같다.

| 묶음 | 건수 | 정답 |
|---|---|---|
| 다섯 유형 (표기 5종 × 샘플 0/5/20행, 설명 시트, 제목 줄, 필수 열 누락, 같은 유형 시트 여러 개 등) | 140 | 추천 |
| 열이 최소이거나 일반 표기라 헷갈리는 정답 사례 | 14 | 추천, 보류도 인정 |
| 변환이 필요한 자료 (판매 주문, 출고 내역, 가로 월별 표) | 18 | 보류 + monthly_demand 안내 |
| capacity, routing | 16 | 보류 |
| 그 밖의 업무 보고서 | 27 | 보류 |
| 무관한 자료 | 20 | 보류 |
| 열 이름만으로 정할 수 없는 자료, 유형이 섞인 통합 문서 | 19 | 보류 |
| 내용이 없거나 구조를 알 수 없는 파일 | 9 | 보류 |

기대 결과 필드: `expected_entity`(올바른 추천, 없으면 null), `must_hold`(보류만 정답), `hold_ok`(보류해도 오분류로 보지 않음), `guidance_entity`(보류하되 변환 대상 안내).

### 측정 결과

| 대상 | 건수 | 올바른 추천·보류 | 오분류 | 추천해야 하는데 보류 |
|---|---|---|---|---|
| 자체 시험 사례 | 263 | 263 | 0 | 0 |
| 백엔드 매핑 별칭으로 만든 열 조합, 규칙 수정 전 (`rules-0.1.0`) | 2,500 | 1,543 (62%) | 22 | 935 |
| 같은 열 조합, 규칙 수정 후 (`rules-0.2.0`) | 2,500 | 2,450 (98%) | 0 | 50 |

응답시간은 사례당 0.1ms 안팎이다(분류 함수만).

---

## 2. 문서 종류 분류 (`doctype.py`)

엑셀 파일을 종류 표시 없이 넣으면 아래 범주로 나눈다. 확신이 부족하면 범주 대신 `확인 필요`로 남긴다.

| 범주 | 파일의 모습 |
|---|---|
| BOM | 제품별 구성품과 소요량 |
| MPS | 제품 × 주/월별 생산계획 수량 |
| MRP | 자재 × 기간별 총소요·예정입고·순소요·계획발주 |
| RCCP | 주요 설비 × 월별 필요시간과 가용시간 (개략) |
| CRP | 작업장·공정·오더별 상세 부하 |
| MES | 현장 실적 (양품·불량, 설비 가동, LOT) |
| ERP | 기준정보와 거래 (제품·자재 마스터, 수주, 발주, 입고, 재고, 단가) |
| 미분류 | 위에 해당하지 않는 문서 |

### 판단 방식

1. 시트마다 열 이름 줄을 찾는다(글자 칸이 가장 많은 줄). 그 위쪽은 제목 영역으로 본다.
2. 제목, 열 이름, 왼쪽 열의 항목 이름에서 범주별 단서 낱말을 찾아 가중치를 더한다. 약어(MRP, MES 등)는 낱말 경계를 지켜 찾는다.
3. 구조 규칙을 적용한다.
   - 부하·능력 표는 기간 단위로 가른다: 월 단위면 RCCP, 주·일 단위면 CRP 쪽으로 기운다.
   - 기간이 가로로 놓인 격자는 계획 문서로 보고 ERP 점수를 절반으로 낮춘다.
   - RCCP 문서가 MPS를 언급하는 것만으로는 MPS로 보지 않는다.
4. 1순위 점수가 3 이상이고 2순위와 1.5 이상 차이 날 때만 범주를 정한다. 아니면 `확인 필요` 또는 `미분류`다.

점수는 단서 낱말 가중치의 합이며 확률이 아니다. 파일명은 판단에 쓰지 않는다.

### 더미 엑셀 200개 (SYNTHETIC)

`samples/make_samples.py`가 범주당 25개씩 실제 `.xlsx`를 `samples/inbox/`에 만든다. 가상 회사 ㈜충파모제지 한 곳의 자료이고 수치는 모두 가정이다.

공개 자료에서 확인한 실제 표 형태를 본떴다. 형태별 출처는 `labels.json`의 `source`, `verified`에 있다.

| 출처 | 본뜬 형태 | 글자로 확인 |
|---|---|---|
| Oracle Capacity User's Guide 12.1 | RCCP 예시 표 4종 (Load Ratio, Bill of Resources 등) | 예 |
| Oracle Master Scheduling/MRP 12.1 | 일정·예측 입력 표 | 예 |
| Wikiversity, CPIM 학습 자료 | MPS 격자 (Forecast, PAB, ATP, WK 0~10) | 예 |
| Kurbel ERP 교재 | 구조표, 재고 구분, 거래처·공급사 속성 | 예 |
| 국내 서식 설명, ERP 블로그 | 생산일지, 주간 생산현황표, 불량품현황, MRP 항목 용어, 설비종합효율 용어 | 예 (설명문 기준) |
| SAP 표준 화면 (CS12, MD04, CM01, 실적 조회) | 열 이름 | 아니오 (공개 문서에 화면 캡처뿐) |
| 교재식 MRP 레코드 격자 | 행 이름 | 아니오 |

반영한 모양: 표 위의 키-값 머리 정보, 품목마다 반복되는 레코드 묶음, 두 줄짜리 병합 머리글, 결재란·작성일자·부서, 숫자뿐인 기간 열, 실제 날짜 셀, 합계 줄, 출력일시 꼬리말. 자료 시트는 9~152줄(중앙값 약 53줄)이고 표지 시트는 20개 중 1개꼴이다.

### 측정 결과

| 대상 | 정답 | 확인 필요 | 미분류로 놓침 | 다른 범주로 오분류 |
|---|---|---|---|---|
| 더미 v1 200, 규칙을 처음 쓴 직후 (`doctype-0.1.0`) | 177 (88.5%) | 4 | 16 | 3 |
| 더미 v1 200, 보완 후 (`doctype-0.2.0`) | 195 (97.5%) | 5 | 0 | 0 |
| 더미 v2 200, 규칙을 고치지 않고 (`doctype-0.2.0`) | 136 (68%) | 15 | 40 | 9 |
| └ 출처를 글자로 확인한 형태 94 | 41 (44%) | 12 | 37 | 4 |
| └ 확인하지 못해 내 지식으로 쓴 형태 106 | 95 (90%) | 3 | 3 | 5 |
| 더미 v2, 보완 후 dev 91 (`doctype-0.3.0`, 고칠 때 본 것) | 91 | 0 | 0 | 0 |
| 더미 v2, 보완 후 test 109 (고칠 때 보지 않은 것) | 109 | 0 | 0 | 0 |
| 다른 난수 시드로 새로 만든 600 | 600 | 0 | 0 | 0 |
| 글자 칸의 30%를 모르는 낱말로 바꿈 (200) | 195 | 1 | 4 | 0 |
| 글자 칸의 50%를 모르는 낱말로 바꿈 (200) | 174 | 5 | 21 | 0 |
| 글자 칸의 70%를 모르는 낱말로 바꿈 (200) | 153 | 7 | 37 | 3 |

파일당 처리시간은 중앙값 약 14ms, 최대 약 60ms다(엑셀 읽기 포함, 개발 PC).

---

## 시도한 것과 배운 것

날짜순이다. 숫자는 위 표와 같다.

1. **테이블 분류기를 만들고 자체 사례 263건을 전부 맞혔다.** 사례와 규칙을 같은 어휘로 만들었으니 당연한 결과였다.
2. **백엔드 매핑 별칭으로 열 조합 2,500건을 만들어 넣었다.** 남이 만든 어휘에서는 정답 62%, 오분류 22건(모두 월 수요를 제품 마스터로 추천)이었다. 기간·수량 열 이름을 몰라서 생긴 문제라, 모르는 열 이름에 기간·수량을 뜻하는 말이 있으면 마스터로 추천하지 않도록 고쳤다. 고친 뒤 98%, 오분류 0건.
3. **요구가 "엑셀 200개를 종류 구분 없이 넣으면 문서 종류별로 나누기"로 바뀌어 문서 종류 분류기를 따로 만들었다.** 규칙을 먼저 쓰고 더미(v1)를 나중에 돌려 첫 결과 88.5%를 얻었다. 틀린 3건은 모두 RCCP를 CRP로 본 것이었다. 보완 후 97.5%.
4. **더미 v1이 실제 문서와 너무 다르다는 지적을 받았다.** "열 이름 한 줄 + 데이터"인 깔끔한 표뿐이었다. 실제 표 형태를 검색해 v2를 다시 만들었다. 국내 ERP(더존, 이카운트, 영림원)의 실제 내려받기 양식과 SAP 화면의 열 이름은 공개 자료에서 글자로 확인하지 못했다.
5. **분류기를 고치지 않고 v2에 돌리니 68%로 떨어졌다.** 출처를 확인한 형태에서는 44%, 내 지식으로 쓴 형태에서는 90%였다. 분류기가 "만든 사람이 아는 어휘"에만 맞춰져 있었다는 뜻이다.
6. **v2 첫 판은 열면 표지 시트만 보이고 자료가 대여섯 줄뿐이었다.** 표지를 줄이고, 열면 자료 시트가 보이게 하고, 파일마다 자료를 9~152줄로 늘렸다.
7. **v2의 dev 분할에서 놓친 사례만 보고 보완했다(`doctype-0.3.0`).** 영문 시스템 표기와 국내 서식 낱말을 더하고, `Reorder level`을 BOM으로, `Shop-floor stock`을 MES로 보던 오탐을 고치고, 구조 규칙 두 개를 넣었다. dev·test·새 시드에서 모두 맞혔다.
8. **낱말을 일부러 가려 보았다.** 글자 칸의 절반을 모르는 낱말로 바꿔도 오분류는 0건이고, 틀리는 대신 미분류·확인 필요로 빠졌다.

배운 것:
- 더미와 규칙을 같은 사람이 만들면 점수는 항상 높게 나온다. 새 어휘나 새 형태를 만날 때마다 60%대로 떨어졌다(62%, 68%).
- 그래서 "정답률"보다 "모를 때 틀리지 않고 보류하는가"가 더 믿을 만한 지표였다.
- 임베딩 검색 실험(별도 저장소 `retriever-eval`)에서도 같은 결론이었다: 순위는 잘 매기지만 "비슷하지만 다른 것"을 걸러내지 못해 오분류가 나온다. 규칙이 먼저 판정하고 애매하면 보류하는 구성을 택한 이유다.

## 한계

- 실제 기업 파일, 다른 사람이 만든 파일로는 측정하지 않았다.
- 문서 종류 분류의 100%는 같은 표 형태 30여 종 안에서의 결과다. test 분할의 틀린 사례 목록은 보완 전에 한 번 본 적이 있어 완전히 가려진 것도 아니다. 새로운 회사의 양식을 만나면 정답률은 다시 떨어질 것으로 본다.
- 더미는 가상 회사 한 곳, 한 업종뿐이다.
- 기준값(테이블 분류의 0.6/0.7/0.15, 문서 종류 분류의 3.0/1.5와 낱말 가중치)은 담당자가 합성 자료로 정했다. 팀 합의가 필요하다.
- ERP는 "다른 여섯 범주에 해당하지 않는 기준정보·거래 자료"로 정의했다. BOM이나 재고도 ERP에서 나오므로 경계는 팀 합의가 필요하다.
- 테이블 분류는 capacity·routing을 추천하지 않는다(분류 계약의 entity가 5종).
- 문서 종류 분류는 HTTP API와 UI에 연결되어 있지 않다. 지금은 `tools/sort_folder.py`로만 쓴다.
- 분류기가 501을 반환한다고 가정한 통합 담당 소유 테스트(`backend/tests/test_module_integration.py`의 `test_unimplemented_modules_are_errors_...`, `tests/e2e/browser/handoff.spec.ts` 26줄)는 이 모듈에서 고칠 수 없어 그대로다.

## 앞으로

- 실제 파일에서 `미분류`·`확인 필요`가 나오면 그 파일의 낱말을 `doctype.py`의 단서 목록에 더한다.
- 팀원이나 수요기업의 실제 엑셀을 받아 `sort_folder.py`로 그대로 돌려 본다. 지금 가장 값진 검증이다.
- UI가 준비되면 문서 종류 분류를 화면에 연결한다(API 주소와 응답 형태는 김대영과 확정).

## 출처

- Oracle Capacity User's Guide 12.1, Rough Cut Capacity Planning: https://docs.oracle.com/cd/E18727_01/doc.121/e15189/T473818T474769.htm
- Oracle Master Scheduling/MRP 12.1: https://docs.oracle.com/cd/E18727-01/doc.121/b31558/T478564T478750.htm
- Wikiversity, Master Production Schedule: https://en.wikiversity.org/wiki/Master_Production_Schedule
- CPIM study guide, Creating the Master Schedule: https://open-exam-prep.com/study-guides/cpim/master-scheduling/creating-master-schedule
- Kurbel, MRP: Material Requirements Planning: https://faculty.ksu.edu.sa/sites/default/files/MRP-%20Material%20Requirements%20Planning.pdf
- SAP Help, Displaying the Capacity Load / Stock/Requirements List (4.6C)
- 비즈폼 생산일지·불량품현황 서식 설명, 아이퀘스트 블로그 MRP·BOM 글
