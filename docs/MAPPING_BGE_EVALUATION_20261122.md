# BGE-M3 컬럼 추천 비교와 적용 결정

2026-11-22 KST, 기존 개발 PC, 시작 `main` `6e7056aeb09166b2bc82d994faaae47f5af15db9`. **BGE-M3는 새로운 헤더의 후보 검색을 개선했지만 안전 조건을 통과하지 못해 API에는 연결하지 않았다.** RapidFuzz Top-3는 유지하고 재현된 업무 의미 충돌을 차단했다. [비교 기준 커밋](https://github.com/ChungPaMo/decision-supporter-mvp/commit/6e7056aeb09166b2bc82d994faaae47f5af15db9)

## 같은 합성 48건에서 측정한 결과

[고정 평가셋](../contracts/examples/mapping_recommendation_cases_v1.json)은 정답 있는 32개와 모호·충돌·무관으로 정답을 정할 수 없는 16개다. 파일 SHA-256은 `7df6ea18a15c2f08cbd81a7e2ada9ad98e0248def9da8bdaaa08cf1be45ffd67`이다. 기존 별칭과 필드 집합을 사용했으며 모델 전용 별칭이나 평가셋 임계값 탐색은 추가하지 않았다. exact·strong·weak alias, 프로파일·의미 반증은 공통 추천 코드를 적용했다.

| 방식 | Top-1 / 32 | Top-3 / 32 | 오추천 Top-1 / 48 | 후보 HOLD / 48 | 지연 중앙값 / P95 ms | RSS / Windows 최대 working set MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RapidFuzz, 보강 후 | 25 (78.13%) | 26 (81.25%) | 3 (6.25%) | 20 (41.67%) | 0.15 / 0.32 | 55.6 / 55.6 |
| BGE-M3 dense + 공통 검사 | 31 (96.88%) | 32 (100%) | 7 (14.58%) | 10 (20.83%) | 45.39 / 53.65 | 1,512.0 / 1,512.0 |
| RapidFuzz 유지 + BGE 빈 슬롯 보완 | 31 (96.88%) | 32 (100%) | 7 (14.58%) | 10 (20.83%) | 45.63 / 57.06 | 1,512.1 / 1,512.1 |

정답 null인데 후보를 주거나 정답 필드와 다른 첫 후보를 주면 오추천이다. HOLD는 후보가 없는 **열**의 비율이다. 실제 파일 HOLD, 자동 매핑, 승인 정확도와 분모가 다르다. 정답 null인데 후보를 낸 열은 RapidFuzz 2/16, dense와 보완 방식 각각 6/16이었다. 해당 열의 전체 후보 수도 3개에서 11개로 늘었다. 시작 커밋 코드도 이번 PC에서 같은 48건으로 다시 실행했다. Top-1 25/32와 Top-3 26/32는 보강 전후 같고, 오추천은 6→3건, 후보 HOLD는 17→20건이었다. 과거 연구 수치는 이 표에 포함하지 않았다.

실제 개선 사례 6건은 `calendar_month`→`period`, `완제품식별번호`→`product_id`, `원자재식별번호`→`material_id`, `item_classificaton`→`item_type`, `stock_snapshot_date`→`as_of_date`, `quantity_per_assembly`→`qty_per`다. 반면 `월수요金額`에 `period`·`unit`, `현재고/가용재고`에 `allocated_qty` 등, `base_or_available_qty`에 `allocated_qty`, `거래처약칭`에 `material_name`을 후보로 냈다. 결합 방식은 RapidFuzz가 이미 낸 순서를 유지해도 기존 HOLD 열의 첫 후보가 틀릴 수 있다. 보강 후 RapidFuzz의 남은 오추천은 `product_categroy`→`product_id`, 문맥 없는 `수량`→`demand_qty`, `참고기간`→`period`다. 사용자 검토가 필요하다.

사전 비교 조건은 보완 방식의 Top-3 정답이 2건 이상 증가하고 Top-1이 감소하지 않으며, 잘못된 Top-1 및 정답 없는 열의 후보 수가 증가하지 않는 것이다. 새 맞춤 규칙으로 같은 48개 정답을 최적화하더라도 이 셋만으로 일반화할 수 없다. 이번에는 오추천 조건을 충족하지 못했다. 별도로 약 46ms의 열별 중앙값, 약 1.48GiB의 프로세스 메모리도 배포 판단에 반영했다.

## 연구와 모델 재사용

연구 저장소 `c7f3fce8c81c3365c00cc36295427709c9baa6af`의 `scripts/trichef_experiment.py`를 확인했다. `s0_im` dense에서 CLS 벡터를 취하고 L2 정규화한 뒤 내적하는 부분을 재사용했다. 연구 전체의 후보 집합, 희소 점수, SigLIP2, 점수 조정과 실험용 의존성은 포함하지 않았다. 이번에는 BAAI의 FP32 ONNX `5617a9f61b028005a4858fdac845db406aefb181`과 동일한 서버 별칭의 원문을 사용했다. 벡터 정규화 후 별칭별 최대 코사인 점수, 고정 cutoff 0.60을 사용했다. 이 점수는 승인 기준이나 확률이 아니다. [연구 코드](https://github.com/ChungPaMo/retriever-eval/blob/c7f3fce8c81c3365c00cc36295427709c9baa6af/scripts/trichef_experiment.py) · [BAAI 모델 카드](https://huggingface.co/BAAI/bge-m3)

Python 3.11.9, RapidFuzz 3.14.6, ONNX Runtime 1.32.0, tokenizers 0.23.3. CPU 4스레드, FP32, 그래프 최적화 끔으로 시험했다. 첫 실행의 모델·별칭 인덱스 준비는 5.68초였다. 모델 로드와 입력 CSV 파싱 뒤 각 열을 단건으로 3회 처리해 중앙값과 P95를 구했다. 추천의 프로파일과 반증 비용은 포함하고 파일 I/O·네트워크·HTTP·DB는 제외했다. RSS/working set은 같은 프로세스에서 모델 로드 전후를 측정했다. BGE와 보완 방식은 같은 모델 인스턴스를 공유했다. GPU는 사용하지 않았다. 네 모델 파일 지문을 검증한 재실행에서도 후보 순위와 채택 결정은 같았다. 보완 방식의 재실행 중앙값은 41.47ms, 최대 working set은 1,512.8MiB였다. 48개 합성 사례와 이 실행 조건만을 반영한 결과다.

평가 스크립트는 고정 합성 입력과 네 모델 파일 SHA만 허용한다. 모델은 로컬 파일로 로드하고 임베딩 입력으로 헤더·서버 별칭만 사용한다. 공개 모델 파일과 연구 코드 다운로드 외에 파일·셀 값·승인 자료를 외부 서비스로 전송하지 않았다. 모델·다운로드 의존성·상세 출력은 Git 제외 `.artifacts/mapping-bge-eval/`에 있다. 평가 의존성은 운영 requirements와 분리했다. [재현 스크립트](../scripts/evaluate_mapping_bge.py)

```powershell
# 모델 디렉터리에는 고정 리비전의 onnx/model.onnx, model.onnx_data,
# Constant_7_attr__value, tokenizer.json을 보관한다.
.\.venv\Scripts\python.exe -m pip install --target .artifacts/mapping-bge-eval/deps onnxruntime==1.32.0 tokenizers==0.23.3 psutil==7.2.2
$env:PYTHONPATH = (Resolve-Path .artifacts/mapping-bge-eval/deps).Path
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:OPENBLAS_NUM_THREADS = '1'
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_mapping_bge.py .artifacts/mapping-bge-eval/onnx
```

## API와 승인 흐름

`POST /ingest/mapping-suggestions`와 `/ingest/classified-mapping`의 요청·응답 타입, Top-3와 `LEXICAL_SIMILARITY` 근거 표시는 그대로다. 새 모델 옵션, 운영 모델 로더, 외부 호출은 추가하지 않았다. 로컬 모델이 없는 서버에서도 기존 RapidFuzz 경로가 동작한다. 추천 단계에서는 한자 금액, 재고 평가액, 출고 수량 및 기준/가용 혼용 열이 해당 수량 역할로 채택되는 일을 차단한다. 정확 매퍼·수동 선택·정책 확인·저장·승인 로직은 기존 계약을 따른다. [추천 구현](../backend/app/ingest/recommendation.py)

공식 합성 판매 원장 한 행에서 이름을 바꾼 수량 열과 금액 열로 회귀 테스트를 만들었다. 추천 HOLD에서 사용자가 수량 열을 명시해도 `user_confirmed=false`인 변환은 `POLICY_REVIEW_REQUIRED`였다. 확인 후 미리보기의 수량이 선택한 열과 일치했고, `POST /ingest/transformations`는 `READY_FOR_APPROVAL`로만 저장했다. 승인 수요는 0행이었다. 전체 공식 원장 변환·검증·승인 흐름도 기존 테스트로 실행했다. [API 회귀 테스트](../backend/tests/test_ingestion_api_e2e.py)

- 개발 PostgreSQL `0009`는 강제 읽기 전용으로 연결해 같은 데이터셋의 승인 마스터를 사용하는 추천 200/HOLD를 확인했다. DB 60개 테이블과 스키마 객체 735개 지문, 승인 배치와 예측 이력이 전후 일치했다.
- `chungpamo_regression` `0009`의 전용 역할·sentinel·빈 시험 범위를 확인한 뒤 같은 API 테스트를 실제 PostgreSQL 저장소로 실행했다. 외부 트랜잭션 안에서 이력 1건·원본 1건·승인 전 배치와 공개 수요 0행을 확인했다. 지연 제약을 검사하고 전체 롤백했으며 비교 테이블 34개의 행 수와 지문은 같았다. 공식 원본 14개 SHA도 대조했다.
- 최종 전체 비DB pytest **1,114 passed / 0 failed / 66 skipped / 0 deselected**. 최초 테스트의 스테이징 요청에서 필수 `created_by`가 빠져 422가 났고 테스트 요청을 수정한 뒤 통과했다. TypeScript·Vite 빌드, OpenAPI·Schema 동기화 검사 통과. 초기화가 필요한 DB pytest와 브라우저는 미실행이다.
- 변경 파일의 보안 검사 발견은 0건이다. 전체 트리 검사에 나타난 결과는 기존 분류기 Excel 200건과 합성 전화번호 생성 코드 1건이며 시작 커밋의 파일과 대조했다.
