# 엑셀 문서 자동 분류기 · 이훤

엑셀 파일을 종류 표시 없이 한꺼번에 넣으면, 각 파일이 **BOM / MPS / MRP / RCCP / CRP / MES / ERP** 중 무엇인지 알아서 나눠 준다. 확신이 없으면 틀리게 말하지 않고 사람에게 확인을 요청한다.

## 한눈에 보는 결과

**처음 보는 양식의 엑셀 100개 중 91개를 맞게 분류한다.** 이전에는 75개였다.

![처음 보는 엑셀 100개를 넣었을 때 이전과 지금](figures/1_waffle.png)

![핵심 숫자 세 가지](figures/2_before_after.png)

- **맞게 분류한 비율이 75%에서 91%로 올랐다.**
- **"모르겠다"고 넘기던 파일이 19건에서 1건으로 줄었다.** 사전에 없는 낱말이 나와도 뜻으로 알아본다.
- **틀리게 분류한 파일이 5건에서 1건으로 줄었다.** 두 가지 판단이 서로 다르면 사람에게 확인을 요청하기 때문이다.

약하던 문서 종류일수록 많이 올랐다. 현장 실적(MES)은 27%에서 73%로, BOM은 62%에서 100%로 올랐다.

![문서 종류별 변화](figures/3_by_category.png)

여러 방식을 시험했고, 효과가 있는 것만 남겼다.

![시도한 방식별 결과](figures/4_methods.png)

> **숫자를 읽을 때 알아 둘 점.** 위 결과는 분류기가 **본 적 없는 양식**의 엑셀 109개로 잰 값이다. 엑셀은 실제 문서 형태를 본떠 만든 합성 자료이고, 실제 기업 파일로 잰 값은 아니다. 이미 본 양식에서는 200개 중 196개를 맞히고 나머지 4개는 확인을 요청하며, 틀리게 분류한 것은 없다.

## 어떻게 알아보나

두 가지 방법을 함께 쓴다.

1. **낱말 사전.** 파일의 제목, 열 이름, 항목 이름에서 `총소요량`, `순소요량` 같은 낱말을 찾으면 MRP로 본다. 빠르고 확실하지만, 사전에 없는 낱말이 나오면 알아보지 못한다.
2. **낱말의 뜻.** 사전에 없는 낱말은 뜻이 가까운 기준 용어에 연결한다. 예를 들어 `정품수량`은 사전에 없어도 `양품 수량`과 뜻이 가까우므로 현장 실적(MES)의 단서로 센다. AI 임베딩 모델(BGE-M3)을 쓰며, 내 컴퓨터 안에서만 돌고 파일 내용을 밖으로 보내지 않는다.

둘을 합치는 규칙:

- 사전이 정하지 못한 파일은 뜻으로 판단한다.
- 사전과 뜻이 **서로 다른 답**을 내면 어느 쪽도 믿지 않고 "확인 필요"로 돌린다.
- 인사·회의록·점검표처럼 무관한 문서의 용어에 더 가까우면 "미분류"로 둔다.

## 무엇으로 나누나

| 종류 | 파일의 모습 |
|---|---|
| BOM | 제품별 구성품과 소요량 |
| MPS | 제품 × 주/월별 생산계획 수량 |
| MRP | 자재 × 기간별 총소요·예정입고·순소요·계획발주 |
| RCCP | 주요 설비 × 월별 필요시간과 가용시간 (개략) |
| CRP | 작업장·공정·오더별 상세 부하 |
| MES | 현장 실적 (양품·불량, 설비 가동, LOT) |
| ERP | 기준정보와 거래 (품목·거래처, 수주, 발주, 입고, 재고, 단가) |
| 미분류 | 위에 해당하지 않는 문서 |
| 확인 필요 | 분류기가 확신하지 못한 파일 |

## 사용법

```powershell
# 폴더를 통째로 분류해 결과 엑셀을 만든다 (낱말 사전만)
python -X utf8 modules/file_classifier/tools/sort_folder.py <폴더> --out 분류결과.xlsx

# 낱말의 뜻까지 함께 쓴다 (권장. torch, transformers 필요, GPU 권장)
python -X utf8 modules/file_classifier/tools/sort_folder.py <폴더> --out 분류결과.xlsx --embed

# 더미 엑셀 200개 만들기, 위 그림과 숫자 다시 만들기, 시험
python -X utf8 modules/file_classifier/samples/make_samples.py
python -X utf8 modules/file_classifier/tools/make_figures.py
./.venv/Scripts/python.exe -m pytest modules/file_classifier -q
```

결과 엑셀에는 파일명, 분류, 확신 정도, 근거가 적힌다. 원본 파일은 읽기만 하고 옮기거나 고치지 않는다. 폴더 분류와 더미 생성에는 openpyxl이 필요하다.

## 구성

| 경로 | 내용 |
|---|---|
| `src/file_classifier/doctype.py` | 낱말 사전 규칙 (`doctype-0.3.0`) |
| `src/file_classifier/doctype_embed.py` | 낱말의 뜻으로 판단, 사전과 합치기 (`doctype-embed-0.1.0`) |
| `tools/sort_folder.py` | 폴더 일괄 분류 → 결과 엑셀 |
| `tools/eval_embed.py`, `tools/make_figures.py` | 측정 실험, 그림 생성 |
| `samples/make_samples.py`, `samples/labels.json` | 더미 엑셀 200개 생성기와 정답 |
| `figures/` | 위 그림 4장과 그림에 쓴 숫자(`numbers.json`) |
| `src/file_classifier/rules.py`, `__init__.py` | 업로드 화면용 테이블 분류 (아래 "이전 연구 요약" 참고) |
| `tests/` | 시험 300개 |

`.xlsx`와 `.csv`는 저장소 `.gitignore` 대상이라 더미 파일과 결과 파일은 올라가지 않는다. 생성기로 다시 만든다.

## 자세한 수치

처음 보는 양식 기준(더미 v2의 test 분할 109개). "사전만"은 이 더미를 보기 전의 사전으로 되돌린 것이다.

| 구성 | 맞게 분류 | 확인 요청 | 모르겠다고 넘김 | 틀리게 분류 |
|---|---|---|---|---|
| 사전만 | 82 (75.2%) | 3 | 19 | 5 |
| 뜻만 | 91 (83.5%) | 7 | 9 | 2 |
| **사전 + 뜻** | **99 (90.8%)** | 8 | 1 | 1 |

이미 본 양식 기준(전체 200개, 지금의 사전).

| 구성 | 맞게 분류 | 확인 요청 | 모르겠다고 넘김 | 틀리게 분류 |
|---|---|---|---|---|
| 사전만 | 200 | 0 | 0 | 0 |
| 사전 + 뜻 | 196 (98.0%) | 4 | 0 | 0 |

- 처리시간: 파일당 약 14ms(사전만), 약 57ms(사전 + 뜻, GPU, 모델을 올리는 시간 제외). CPU에서는 재지 않았다.
- 기준값: 낱말 유사도 0.65 이상만 단서로 세고, 종류 점수 1.5 이상, 2순위와 0.6 이상 차이. 점수는 확률이 아니다.
- 낱말을 일부러 가려 본 결과(사전만, 200개): 글자 칸의 절반을 모르는 낱말로 바꿔도 틀리게 분류한 것은 0건이었다.

## 한계

- **실제 기업 파일로는 재지 않았다.** 더미는 가상 회사(㈜충파모제지) 한 곳의 합성 자료다. 표 형태는 공개 자료에서 확인한 것을 본떴지만 수치는 가정이다.
- 국내 ERP(더존, 이카운트, 영림원)의 실제 내려받기 양식과 SAP 화면의 열 이름은 공개 자료에서 글자로 확인하지 못했다.
- "처음 보는 양식" 측정도 완전히 독립적이지는 않다. 뜻 판단에 쓰는 기준 용어는 통용 용어로 골랐지만 더미를 본 뒤에 썼다.
- 뜻 판단은 torch·transformers와 GPU가 있어야 실용적이다. HTTP API와 화면에는 아직 연결하지 않았다.
- ERP는 "다른 여섯 종류에 해당하지 않는 기준정보·거래 자료"로 정의했다. 경계와 기준값은 팀 합의가 필요하다.
- 분류기가 501을 반환한다고 가정한 통합 담당 소유 테스트 2개(`backend/tests/test_module_integration.py`, `tests/e2e/browser/handoff.spec.ts` 26줄)는 이 모듈에서 고칠 수 없어 그대로다.

다음 단계: 팀이나 수요기업의 실제 엑셀을 받아 `sort_folder.py --embed`로 그대로 돌려 본다.

---

## 이전 연구 요약

여기까지 오면서 시험한 것들이다. 자세한 수치는 Git 기록의 이전 README에 있다.

| 시도 | 결과 | 배운 것 |
|---|---|---|
| 임베딩 검색으로 열 이름 매핑 (별도 저장소 `retriever-eval`) | 순위는 잘 매기지만 오매핑 9~38% | 뜻만 보면 "비슷하지만 다른 것"을 틀린다. 규칙이 먼저 판정해야 한다 |
| 업로드 화면용 테이블 분류 (`rules.py`, 5종 추천) | 자체 사례 263건 전부 정답. 남이 만든 열 이름 2,500건에서는 62% → 고친 뒤 98%, 오분류 0건 | 문제와 답을 같은 사람이 만들면 점수가 부풀려진다 |
| 문서 종류 분류, 깔끔한 더미(v1) | 88.5% → 97.5% | 더미가 실제 문서와 너무 달랐다 |
| 실제 형태를 본뜬 더미(v2)로 교체 | 사전을 고치지 않으면 68%, 고치면 100% | 새 양식을 만날 때마다 60~70%대로 떨어진다. 사전만으로는 한계가 있다 |
| 파일을 통째로 임베딩해 비교 | 26% | 효과 없음 |
| 정답 예시 파일과 비교 (kNN) | 5% | 다른 양식의 예시는 도움이 안 된다 |
| **낱말 단위로 뜻을 비교해 사전과 합침** | **75% → 91%** | 채택. 이 문서의 맨 위 결과 |

업로드 화면용 테이블 분류(`classify()`, `/classifications` API)는 그대로 동작한다. 열 이름을 보고 product / material / bom / inventory / monthly_demand 중 하나를 추천하거나 보류한다.

## 출처

- Oracle Capacity User's Guide 12.1, Rough Cut Capacity Planning: https://docs.oracle.com/cd/E18727_01/doc.121/e15189/T473818T474769.htm
- Oracle Master Scheduling/MRP 12.1: https://docs.oracle.com/cd/E18727-01/doc.121/b31558/T478564T478750.htm
- Wikiversity, Master Production Schedule: https://en.wikiversity.org/wiki/Master_Production_Schedule
- CPIM study guide, Creating the Master Schedule: https://open-exam-prep.com/study-guides/cpim/master-scheduling/creating-master-schedule
- Kurbel, MRP: Material Requirements Planning: https://faculty.ksu.edu.sa/sites/default/files/MRP-%20Material%20Requirements%20Planning.pdf
- 비즈폼 생산일지·불량품현황 서식 설명, 아이퀘스트 블로그 MRP·BOM 글
- 임베딩 모델: BAAI/bge-m3
