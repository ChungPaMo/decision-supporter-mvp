# 제조업 컬럼 의미 검색 CPU 비교

2026-11-23 KST, 기존 개발 PC, 시작 `main` [`82fa99f`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/82fa99fd2018dee5e73072924e9c7280f7353cda). Qwen3-Embedding-0.6B는 신규 합성셋에서 후보 검색에 가장 유망했다. 전체 문맥을 사용한 Qwen의 Top-3는 29/37이고 오추천은 8/70이었다. 운영 RapidFuzz의 6/37·7/70과 비교하면 후보 회수는 늘었고 오추천은 1건 늘었다. 운영 모델은 RapidFuzz를 유지한다.

## 선정 근거와 라이선스

MMTEB는 다국어 검색·분류·유사도 등 여러 과제를 포함한다. MTEB 한국어 v2는 검색과 분류를 포함한 20개 과제를 제공한다. 두 자료는 한국어 임베딩 후보군을 좁히는 근거로 사용했다. 제조업의 `수요량`·`반품수량`·`생산수량`·`발주수량`을 같은 등록 스키마에서 구분하는 작업은 별도의 아래 합성 시험으로 측정했다. [MMTEB 논문](https://arxiv.org/abs/2502.13595) · [MTEB 한국어 v2](https://leaderboard.mteb.org/benchmark/MTEB(kor,%20v2))

| 후보 | 선정 이유와 실제 형식 | 모델 라이선스 |
| --- | --- | --- |
| RapidFuzz | 현재 운영 별칭·프로파일 경로. 임베딩 가중치 없음 | [MIT](https://github.com/rapidfuzz/RapidFuzz/blob/main/LICENSE) |
| BGE-M3 | 기존 비교 재현과 다국어 dense 기준선. 공식 FP32 ONNX, CLS pooling, 1,024차원 | [MIT 모델 카드](https://huggingface.co/BAAI/bge-m3) · [논문](https://arxiv.org/abs/2402.03216) |
| multilingual-E5-small | CPU 경량 기준. 384차원, 공식 FP32 ONNX, attention-mask mean pooling, `query:`/`passage:` | [MIT 모델 카드](https://huggingface.co/intfloat/multilingual-e5-small) · [논문](https://arxiv.org/abs/2402.05672) |
| Qwen3-Embedding-0.6B | 다국어 지시형 검색. 공식 Q8_0 GGUF, last pooling, 1,024차원, 영문 검색 지시문 | [Apache-2.0 GGUF 모델 카드](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF) · [논문](https://arxiv.org/abs/2506.05176) |

Jina v3와 v5-text-nano 모델 카드의 공개 가중치는 `CC BY-NC 4.0`이며 상업 사용에는 별도 조건이 필요하다. v4는 `Qwen Research License`를 사용하고 Jina는 상업 사용을 허용하지 않는다고 명시한다. 세 모델은 다운로드·실행 후보에서 제외했다. [v3](https://huggingface.co/jinaai/jina-embeddings-v3#license) · [v5-text-nano](https://huggingface.co/jinaai/jina-embeddings-v5-text-nano#license) · [v5 기술 논문, 2026년 개정](https://arxiv.org/abs/2602.15547) · [v4](https://huggingface.co/jinaai/jina-embeddings-v4#license) · [Jina 라이선스 안내](https://jina.ai/en-US/contact-sales/)

## 평가 설계

- [기존 48건](../contracts/examples/mapping_recommendation_cases_v1.json)은 정답 32건·HOLD 정답 16건이다. 먼저 이전 별칭 기반 RapidFuzz·BGE dense·backfill을 동일 코드로 재실행했다. 그 뒤 새 공통 필드 설명 방식으로 세 임베딩을 비교했다. 별칭 기준선의 BGE와 공통 방식의 BGE는 후보 문서와 HOLD 조건이 다르다.
- [신규 70건](../contracts/examples/mapping_semantic_holdout_v1.json)은 정답 37건·HOLD 정답 33건이다. 제품·자재·BOM·재고·월수요 5종을 합성했고, 모델 추론 전에 고정했다. 학습, 임계값 탐색, 평가셋에 맞춘 별칭 수정은 없었다. 월수요의 HOLD 정답에는 목표 등록 스키마가 받지 않는 반품·생산·발주·출고·금액이 포함된다. 같은 `수량`이라도 문서 종류에 따라 다른 정답을 가진다.
- 임베딩은 동일한 필드 설명과 HOLD 후보 설명을 코사인으로 비교한다. 최상위가 지원하지 않는 역할이거나 기존 형식·의미 검사와 충돌하거나 1·2위 차가 `0.02` 미만이면 HOLD다. `0.02`는 사전 고정한 순위 차 기준이다. `header`는 컬럼명, `profile`은 자료형과 합성 샘플 값 추가, `full`은 주변 열과 문서 종류를 추가한다. 세 방식에 동일한 프로파일 안전 검사가 적용된다. RapidFuzz는 운영 별칭·프로파일 경로 그대로 비교했다.
- **Top-1·Top-3**의 분모는 정답 있는 열이다. **오추천**은 잘못된 1순위 또는 HOLD 정답에 후보를 노출한 경우로 전체 열 대비다. **HOLD**는 후보 0개의 전체 열 대비 비율이다. **정답 열 커버리지**는 정답이 있는 열 중 후보를 낸 비율이며, 후보가 정답인지 별도로 Top-1·Top-3에서 평가한다. **필터 전 Top-3**는 기존 프로파일과 호환되는 후보의 상위 3개 중 정답 포함을 뜻한다. 모델의 확률이나 자동 승인 지표로 해석하지 않는다.
- 자료형과 문서 종류는 합성 예제에 입력했다. 실제 파일 자동분류의 오류, 모델별 정밀도 차이, 모델 외 지연은 이 수치에 일반화할 수 없다. BGE와 E5는 FP32 ONNX, Qwen은 Q8_0 GGUF라 수치는 실제 시험한 구현 조합에 해당한다.

## 기존 48건 결과

### 이전 별칭 기반 실험 재실행

| 방식 | Top-1 / 32 | Top-3 / 32 | 오추천 / 48 | HOLD / 48 | 정답 열 커버리지 / 32 | 중앙값 / P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RapidFuzz | 25 | 26 | 3 | 20 | 26 | 0.13 / 0.18 |
| BGE-M3 dense | 31 | 32 | 7 | 10 | 32 | 38.97 / 43.84 |
| RapidFuzz + BGE 빈 슬롯 보완 | 31 | 32 | 7 | 10 | 32 | 38.81 / 47.17 |

기존 후보 품질 게이트는 이번 재실행에서도 실패했다. 새 BGE 결과를 이전 기록의 지연·메모리 수치로 대체하지 않았다. [이전 재현 기준](MAPPING_BGE_EVALUATION_20261122.md)

### 새 공통 필드 설명, 헤더 입력

| 방식 | Top-1 / 32 | Top-3 / 32 | 오추천 / 48 | HOLD / 48 | 정답 열 커버리지 / 32 | 중앙값 / P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RapidFuzz 운영 경로 | 25 | 26 | 3 | 20 | 26 | 0.14 / 0.22 |
| BGE-M3 | 19 | 21 | 7 | 22 | 21 | 45.76 / 52.14 |
| E5-small | 10 | 11 | 1 | 37 | 11 | 5.87 / 7.35 |
| Qwen3-0.6B Q8_0 | 23 | 23 | 2 | 23 | 23 | 125.40 / 154.00 |

## 신규 70건 홀드아웃 결과

| 방식 | 입력 | Top-1 / 37 | Top-3 / 37 | 오추천 / 70 | HOLD / 70 | 정답 열 커버리지 / 37 | 중앙값 / P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RapidFuzz 운영 경로 | 별칭·프로파일 | 5 | 6 | 7 | 58 | 6 | 0.21 / 0.31 |
| BGE-M3 | 헤더 | 21 | 24 | 12 | 37 | 25 | 46.75 / 52.38 |
| BGE-M3 | + 자료형·값 | 21 | 22 | 7 | 42 | 22 | 77.36 / 100.60 |
| BGE-M3 | + 주변 열·문서 | 25 | 29 | 10 | 35 | 30 | 121.81 / 143.56 |
| E5-small | 헤더 | 5 | 9 | 5 | 60 | 9 | 5.61 / 6.57 |
| E5-small | + 자료형·값 | 7 | 7 | 1 | 62 | 7 | 10.07 / 12.15 |
| E5-small | + 주변 열·문서 | 5 | 5 | 0 | 65 | 5 | 13.57 / 16.24 |
| Qwen3-0.6B Q8_0 | 헤더 | 24 | 26 | 14 | 32 | 26 | 127.01 / 156.23 |
| Qwen3-0.6B Q8_0 | + 자료형·값 | 32 | 34 | 16 | 22 | 34 | 215.98 / 271.36 |
| Qwen3-0.6B Q8_0 | + 주변 열·문서 | 27 | 29 | 8 | 35 | 29 | 335.01 / 413.10 |

Qwen은 자료형·값만 추가하면 Top-1 `24→32`와 오추천 `14→16`이 함께 늘었다. 주변 열과 문서까지 추가하면 오추천이 `16→8`로 줄고 Top-1은 `32→27`이었다. E5 자료형·값은 오추천 `1/70`으로 줄이면서 Top-1 `7/37`을 얻었다. 수요량 정답은 0/9이고, 기존 48건에서는 후보 커버리지가 11/32여서 활용 범위가 좁다. BGE 전체 문맥은 수요량 정답 9/9이며, 전체 오추천은 10/70이다.

### 역할 충돌과 오추천 예시

| 방식 | 수요 정답 / 9 | 반품 오추천 / 5 | 생산 오추천 / 6 | 발주 오추천 / 7 |
| --- | ---: | ---: | ---: | ---: |
| RapidFuzz | 3 | 1 | 2 | 2 |
| BGE-M3 전체 문맥 | 9 | 0 | 0 | 1 |
| E5 자료형·값 | 0 | 0 | 0 | 0 |
| Qwen 헤더 | 8 | 1 | 2 | 2 |
| Qwen 자료형·값 | 9 | 3 | 2 | 3 |
| Qwen 전체 문맥 | 8 | 0 | 0 | 1 |

- `수량`과 샘플 `15, 30`이 같은 행에서 Qwen 전체 문맥은 월별 수요 확정표(`d04`)를 `demand_qty`로 추천했고, 반품 접수(`d13`)·생산실적(`d17`)·구매 발주(`d21`)를 모두 HOLD로 남겼다. RapidFuzz는 세 비수요 열도 `demand_qty`로 추천했다.
- Qwen·BGE 전체 문맥은 `업체 요청 개수`(`d22`)를 `demand_qty`로 잘못 냈다. `계획 청구액`(`d25`)과 `수요 전망액`(`d29`)도 수요로 오분류했다. 숫자형 프로파일만으로는 금액이나 구매 요청을 수요와 구분할 수 없다.
- Qwen 전체 문맥은 `판매 품목 속성군`(`p04`)을 `product_name`으로, `입고표 인쇄 자재명`(`m02`)을 `material_id`로 오추천했다. 올바른 필드가 이미 후보에 있는 경우와 정답 없는 열에 후보가 노출된 경우를 나눠야 한다.

### CPU 비용과 Reranker 판단

Windows Python 3.11.9, Intel Family 6 Model 151 6코어/12스레드·15.8 GiB RAM. 임베딩은 CPU 4스레드, GPU 층 0으로 단독 순차 실행했다. 후보 색인 생성 뒤 워밍업하고 열당 요청을 측정했다. 지연에는 토크나이징·추론·코사인·프로파일 안전 검사, Qwen의 루프백 HTTP가 포함된다. 파일 다운로드·초기화·입력 파싱은 지연에서 제외했다. 메모리는 실행별 Windows 최대 working set이고, Qwen은 Python과 서버의 개별 피크 합으로 상한을 표시했다.

| 방식 | 사용한 모델 파일 합계 | 최대 working set | 추가 런타임 |
| --- | ---: | ---: | --- |
| RapidFuzz 3.14.6 | 0 | 58.5 MiB | Python RapidFuzz |
| BGE-M3 | 2,284,693,904 B | 1,534.4 MiB | ONNX Runtime 1.32.0, tokenizers 0.23.3, NumPy |
| E5-small | 487,351,240 B | 1,150.7 MiB | ONNX Runtime 1.32.0, tokenizers 0.23.3, NumPy |
| Qwen Q8_0 | 639,150,592 B | 809.7 MiB 상한 | llama.cpp b12651 CPU, NumPy |

**항상 적용하는 Reranker는 보류한다.** Qwen 전체 문맥의 필터 전 Top-3에는 37/37 정답이 있었고 노출된 Top-3에는 29/37이었다. 이미 노출된 후보를 재정렬해서 고칠 수 있는 Top-1 오류는 최대 두 건이다. 오추천 8건 중 6건은 HOLD가 정답인 열이라, 후보 순서만 바꾸면 잘못된 추천이 남는다. 우선 반품·생산·발주·금액의 반증이 있는 경우 HOLD를 강제할 수 있는지 독립 평가셋으로 검증한다. 그 뒤 낮은 마진 또는 득점이 엇갈리는 후보에만 **HOLD를 함께 평가할 수 있는 Reranker**를 비교할 의미가 있다. 이번 실험에서는 Reranker 자체를 실행하지 않았다.

## 재현과 Upstage 후속 비교 형식

`scripts/evaluate_mapping_embeddings.py`는 모델 실행과 평가를 분리한다. `--export-inputs`는 두 split의 질의 문장, 대상 엔터티별 후보 설명, SHA를 내보낸다. 정답·정답 여부·포커스 라벨은 내보내지 않는다. 합성 데이터만 사용한다. 개별 모델 파일, 실행 로그, 외부 결과는 `.artifacts/` 아래에 보관한다.

```powershell
$env:PYTHONPATH='.artifacts/mapping-bge-eval/deps'
$env:OMP_NUM_THREADS='4'
$env:OPENBLAS_NUM_THREADS='1'
$out='.artifacts/mapping-model-comparison'
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_mapping_bge.py .artifacts/mapping-bge-eval/onnx --output "$out/legacy-bge-replay.json"
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_mapping_embeddings.py --method rapidfuzz --export-inputs "$out/inputs.json" --output "$out/rapidfuzz.json"
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_mapping_embeddings.py --method bge --model .artifacts/mapping-bge-eval/onnx --output "$out/bge.json"
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_mapping_embeddings.py --method e5 --model "$out/models/e5-small" --output "$out/e5.json"
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_mapping_embeddings.py --method qwen --model "$out/models/Qwen3-Embedding-0.6B-Q8_0.gguf" --llama-server "$out/runtime/llama-server.exe" --output "$out/qwen.json"
```

가중치·토크나이저의 고정 revision과 SHA-256은 평가기에서 검사한다. E5 `614241f…`, Qwen GGUF `370f27d…`, BGE `5617a9f…`를 사용했다. llama.cpp Windows CPU x64 공식 아카이브 SHA-256 `b2d794fa7587aba29f654d717ff9b73e31caeabf50a7766692903008bbe0855d`를 검증했다. [E5 ONNX 파일](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3/onnx) · [Qwen GGUF 파일](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/tree/370f27d7550e0def9b39c1f16d3fbaa13aa67728) · [llama.cpp b12651](https://github.com/ggml-org/llama.cpp/releases/tag/b12651)

별도 Upstage 실험은 같은 질의·후보 문장의 벡터를 계산해 후보별 코사인을 `scores[split][mode][id][candidate_id]`에 채운 JSON과 `bundle_sha256`을 전달한다. HOLD 후보도 점수에 포함한다. `evaluate_mapping_embeddings.py --method score-file --scores <파일> --output <파일>`이 같은 분모·안전 검사·마진으로 채점한다. 외부 호출 시간과 사용량은 실제 호출 측에서 별도로 측정한다. 이번에는 외부 모델 API를 호출하지 않았다.

- 기존 split SHA-256 `7df6ea18a15c2f08cbd81a7e2ada9ad98e0248def9da8bdaaa08cf1be45ffd67`
- 신규 split SHA-256 `0e004d7786c844964c4749ba7c896a06788034589c0c0038ab1e68d75bb95770`
- 입력 묶음 SHA-256 `5ef47e011488ccb52d2d1e4934e2ea4ea044d5c9445b521e56a50690af209cc5`

검증은 전체 `pytest --no-db` **1,220 passed / 0 failed / 67 skipped**, 외부 입력 내보내기의 정답 누출 여부, 동점 점수 파일의 HOLD 및 잘못된 입력 SHA 거부까지 포함했다. 실제 모델·운영 API·PostgreSQL·React 배포 변경은 없다.
