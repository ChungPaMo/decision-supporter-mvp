# 제조업 컬럼 매핑 논문 기반 비교 · Phase 6

2026-11-24 KST · Windows 보조 PC · 김대영

기준 코드 [cf4603d](https://github.com/ChungPaMo/decision-supporter-mvp/commit/cf4603d6b7ebb707f8d32d13d7e2798c9468e5f4)

신규 합성 홀드아웃 200문서·1,736열에서 고정 로컬 정책은 **정답 510/1,175(43.40%), 정밀도 94.97%, 오추천 27/1,736(1.56%), HOLD 정답 거절 552/561(98.40%)**였다. 같은 입력에 Phase 5를 실행한 341정답·68오추천보다 개선했다. 정확 추천율 90%, 정밀도 98%, 오추천율 1% 목표에는 미달했다. 신뢰도 보류 376열과 후보 검색 누락 138열이 가장 큰 병목이다.

## 논문·구현체 조사

arXiv 전문, PMLR, ACL Anthology, ICLR·EDBT proceedings, VLDB 논문과 GitHub 설정·라이선스를 확인했다. 표의 수치는 각 논문의 데이터와 지표에 따른 결과다. 소스 라이선스와 모델·데이터 라이선스는 별도로 확인했다.

| 연구 | 논문의 비교·소거 결과와 공개 구현 | 이번 경량 검증 |
| --- | --- | --- |
| **R01 Correspondences as Decisions: JevNexus for Decision-Centric Schema Matching** · 2026-10 arXiv, 심사 출판 미확인 | GDC-SM과 Valentine 5개군 561사례. Magneto 대비 dataset-macro MRR 0.926→0.930, Hits@1 0.903→0.909, 평균 123.452→15.929초. 순위 차이는 유의하지 않았다. Table 3의 case-macro Hits@1은 증거·재검토 제거 0.856, 상시 재검토 0.896, 선택적 0.925였다. 게이트 발동률 5.665%. MIT 코드의 MPNet Top-20, Open-Jev/COMA++ 고정 결합, Jina Top-3와 vLLM 설정을 확인했다. Jina는 별도 비상업 조건 표기. | HGB Top-3에 헤더·원본 프로파일, 후보별 독립 형식, 증거 불일치·마진 기반 공동 비교를 적용했다. GPU·논문 모델 원본은 미실행. [전문 §4](https://arxiv.org/html/2610.09487v1#S4) · [코드](https://github.com/RazeenLI/JevNexus) |
| **R02 ConStruM: A Structure-Guided LLM Framework for Context-Aware Schema Matching** · 2026-11-04 v3 preprint | HRS-B·PSID-B 415판정. GPT-5.4에서 No-context 51.6%, Full-schema 84.3%, Tree only 81.7%, Differentiation only 88.8%, 전체 95.4%. 작은 모델의 HRS-B는 40.9→48.8%. Table 5의 PSID 27사례에서 트리 없이 16, 전체 트리 27정답. v3에서 공개 실행 저장소는 확인되지 않았다. | Context tree·하이퍼그래프를 작은 업무군·공동 단서 그래프로 단순화했다. 전체 지식, 고정 설명, 후보 대조, 주변 열, 반례, 결합을 수치 특징으로 검증하고 별도 텍스트 바이트 제한을 구현했다. 실제 LM 비교는 미실행. [전문 Tables 1·4·5](https://arxiv.org/html/2601.20482v3) · [저자 논문 목록](https://houmingchen.github.io/page2/) |
| **R03 Bootstrapping Self-Improvement of Language Model Programs for Zero-Shot Schema Matching (Matchmaker)** · ICML 2025 | MIMIC/Synthea→OMOP에서 ReMatch Top-1 42.5/50.5% 대비 62.2/70.2%. 예시 생략 57.9/65.4%, 무작위 55.36/67.76%. 부록 B/C의 ColBERTv2, 검색·추론 후보 각 5개, 합성 예시 최대 4개, confidence/NONE 계약을 확인했다. 저자의 전체 공개 소스·라이선스는 확인되지 않았다. | 고정 검색, 역할 단서로 후보 하나 추가, 절대 confidence로 수용 여부 결정. 학습 예시는 기존 Phase 5 예시와 독립 양식군을 사용했다. 무라벨 LM 자기개선은 미실행. [ICML 논문](https://proceedings.mlr.press/v267/seedat25a.html) · [전문·부록](https://arxiv.org/pdf/2410.24105) |
| **R04 Magneto: Combining Small and Large Language Models for Schema Matching** · PVLDB 18(8), 2025 | GDC·Valentine에서 MPNet 검색 후 GPT-4o-mini 재순위화. Figure 5의 열명·값 샘플·0~1 점수·one-shot·파싱 실패 fallback 확인. GDC Priority/Random MRR 0.591/0.579. fine-tuning에서 LM 합성 데이터 대 단순 변형 MRR 0.754/0.731. Table 6에서 fine-tuned MPNet+LLaMA3.3-70B MRR 0.860. 공개 코드는 Apache-2.0. | 동일 후보에 pointwise·pairwise·listwise·혼합과 NONE을 비교했다. 원시 셀 샘플 전송이나 원본 모델 재학습은 미실행. [전문 §4·6](https://arxiv.org/html/2412.08194v2) · [코드](https://github.com/VIDA-NYU/magneto-matcher) |
| **R05 LLMATCH: A Unified Schema Matching Framework with Large Language Models** · APWeb-WAIM 2025 | SchemaNet의 복합 및 단순 테이블 태스크 11개. 같은 GPT-4o-mini에서 ReMatch 대비 bank1–bank2 F1 0.74→0.85, cms–omop 0.16→0.37. Figure 5/6에서 설명·관계 및 Rollup/Drilldown의 효과가 스키마에 따라 다르다. 코드의 테이블·열 프롬프트 및 MongoDB와 임베딩·채팅 서비스 의존성을 확인했다. 명시 코드 라이선스 미확인. | 역할군 상향 집계 후 원래 필드로 다시 판정했다. 다대다 테이블 정합과 원본 서비스 실행은 미실행. [전문 §6](https://arxiv.org/html/2507.10897v1) · [출판본](https://doi.org/10.1007/978-981-95-5722-6_37) · [코드](https://github.com/knowledge-fusion/LLMatch) |
| **R06 GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning** · ICLR 2026 | 여섯 태스크에서 GRPO 대비 평균 +6%p, 최대 +19%p, 최대 35배 적은 rollout. AIME-2025에서 MIPROv2 대비 +12%p. 실행을 자연어 피드백으로 분석하고 Pareto 후보를 진화시킨다. MIT 코드. | 오류 유형별 평가안을 정리했다. LM 평가·reflection을 수행하는 최적화는 **NOT_RUN**. [ICLR 논문](https://proceedings.iclr.cc/paper_files/paper/2026/hash/0e9e708b6f48e14fd0ac29e167413f76-Abstract-Conference.html) · [코드](https://github.com/gepa-ai/gepa) |
| **R07 Optimizing Instructions and Demonstrations for Multi-Stage Language Model Programs** · EMNLP 2024 및 DSPy MIPROv2 | Llama-3-8B 사용 7태스크 중 5개에서 기존 최적화기보다 높았고 최대 13% 정확도 개선 보고. stage별 bootstrap, grounded instruction, Bayesian search와 소규모 평가 배치를 확인했다. DSPy MIT 코드의 BootstrapFewShot·RandomSearch·MIPROv2·GEPA 지원 확인. | 신규 수동 프롬프트·Bootstrap·MIPROv2·GEPA·동적 예시 LM 비교는 모두 **NOT_RUN**. [논문](https://arxiv.org/abs/2406.11695) · [MIPROv2 공식 코드·설정](https://dspy.ai/current/api/optimizers/MIPROv2/) · [DSPy](https://github.com/stanfordnlp/dspy) |
| **R08 MetaHarmonizer: robust biomedical metadata harmonization and a contamination control for inflated LLM performance on public benchmarks** · 2026 bioRxiv preprint | GDC 165정답의 별칭·값·타입·의미 검색과 별도 ontology 태스크. 배포용 자동 별칭의 GDC Top-1 71.6%를 보고했다. 오염 통제와 exact/fuzzy→값 증거→로컬 인코더→선택형 LM 구조를 확인했다. 명시 코드 라이선스 미확인. | 학습 중 두 양식군 이상에서 동일하게 관측되고 반대 라벨이 없는 별칭만 보탰다. LM 별칭·반례 생성은 미실행. [본문](https://pmc.ncbi.nlm.nih.gov/articles/PMC13308024/) · [코드](https://github.com/sehyunohlab/MetaHarmonizer) |
| **R09 Conformal Risk Control** · ICLR 2024 | 폴립 분할 누락률, 이미지 계층 분류, QA F1의 기대 위험을 다룬다. 교환가능성·단조·유계 조건과 표본 보정항, MIT 코드를 확인했다. 스키마 Top-1 실험은 해당 논문의 연구 범위 밖이다. | 공통·필드·업무 영역 임곗값, logistic/isotonic, risk–coverage, HOLD를 포함한 예측 집합과 문서군 오류 CRC를 각각 검증했다. [논문](https://arxiv.org/abs/2208.02814) · [코드](https://github.com/aangelopoulos/conformal-risk) |

JevNexus의 판별 모델 카드와 모델 설정도 확인했다. [Open-Jev-9B](https://huggingface.co/ZefanCai/Open-Jev-9B)

추가로 **Found in the Middle**(NAACL 2024)은 순열 합의로 다섯 태스크의 위치 편향을 낮췄고 모델별 최대 상대 개선 7–52%를 보고했다. **Position Bias Undermines Preference Consistency in Listwise LLM-Based Reranking**(2026 preprint)은 입력 순서가 쌍별 비교와 최종 순위를 모두 바꿀 수 있음을 보였다. 로컬 pairwise는 양 방향 차이 벡터와 별도의 절대 적합성을 쓴다. LM 순열 호출은 미실행이다. **Collaborative Scoping**(EDBT 2026)의 연결 불가 후보 제거와 **Schema Matching on Graph**(2025 preprint)의 질의별 관계 탐색도 검토했다. 현재 5개 단일 시트 스키마에서는 좁은 역할군·주변 증거를 이용했다. [NAACL 논문 및 코드](https://aclanthology.org/2024.naacl-long.129/) · [위치 편향 연구](https://arxiv.org/abs/2608.03091) · [Collaborative Scoping](https://www.openproceedings.org/2026/conf/edbt/paper-22.pdf) · [SMoG](https://arxiv.org/html/2511.20285)

## 통제 실험 설계

- 후보 검색기는 Phase 5 Train 1,015문서에서 재구성한 HGB로 고정했다. 로컬 판별기만 기존 Development/Calibration 120문서와 새 Development 70문서에서 학습했다. 신규 Selection 110문서로 선택, 별도 Risk 110문서로 보정 진단, Holdout 200문서로 최종 평가했다.
- 분할별 비표준 헤더를 분리하고 알려진 Phase 5 비표준 어휘와 비교했다. 공통 표준 헤더와 구조 유형 일부는 공유한다. 홀드아웃은 40문서군의 합성 자료이며 실제 회사 자료나 별도 전문가 정답을 포함하지 않았다.
- 후보별 MATCH, NON_MATCH, HOLD, TRANSFORM_REQUIRED를 구분했다. 원본 형식 조건은 유지하고, 확신·상호 충돌·대상 유일성을 확인한다. 순위 상단이라도 절대 적합성 미충족 시 보류한다. 변환 후보는 등록 후보 Top-3에서 제외한다.
- HGB Top-1/3/5/전체와, 점수가 낮을 때 강한 역할 단서를 가진 후보를 하나 추가하는 Top-3 확장을 비교했다. 문서 공동 비교에는 원본 열마다 독립 HOLD 위치가 있다. 증거 패킹은 열당 560바이트에서 경쟁 역할과 주변 열·형식 집계를 구성한다.

| 고정 항목 | SHA-256 |
| --- | --- |
| Selection | d458faa7db2b7c35ea23cf7bafbd44fa0dc7424a009ed7296c7dc5b80152a072 |
| Risk | adbcd7784c62ce6ed4aee58fb0ab302bc2e4c4915f7a74eec90dc0c964127434 |
| Holdout | da519e42f1ea5669693c22746e025bc0d24c2ee96c31e0173ef0d517b6d59ad0 |
| 최종 정책 | 982afec43aa95bfff1768c5a151602dafcafe08b0c14a6c155936ea484e3fb9a |

## 동일 신규 홀드아웃 비교

각 방법의 임곗값과 마진을 Selection에서 먼저 고정했다. 별칭을 제외한 A15 조합을 최종 정책 A18로 택했다. 홀드아웃의 다른 결과를 보고 정책을 변경하지 않았다.

| ID·방식 | 정답 / 1,175 | 오추천 / 1,736 | 완전 일치 / 200 |
| --- | ---: | ---: | ---: |
| A01 기존 Exact/RapidFuzz | 211 | 3 | 32 |
| A02 기존 HGB+BM25 | 341 | 68 | 20 |
| A05 Typed 독립 판정 | 384 | 4 | 30 |
| A06 선택적 Listwise | 510 | 20 | 28 |
| A07 전체 지식 / 고정 설명 | 402 / 421 | 50 / 80 | 27 / 26 |
| A07 후보 대조 / 주변 열 | 437 / 430 | 28 / 7 | 28 / 29 |
| A07 혼동 반례 / 결합 | 393 / 510 | 13 / 20 | 29 / 28 |
| A08 근거 있는 후보 확장 + confidence | 514 | 20 | 28 |
| A09 Pointwise | 340 | 74 | 18 |
| A10 Pairwise / A11 Listwise | 510 / 510 | 20 / 20 | 28 / 28 |
| A11 Pairwise+Listwise | 509 | 17 | 28 |
| A12 Rollup/Drilldown | 510 | 20 | 28 |
| **A15/A18 최종 정책, 자동 별칭 제외** | **510** | **27** | **28** |
| A18 형식 특징 제거, Hard 검증 유지 | 474 | 37 | 25 |
| A18 Top-1 / Top-5 / 전체 | 456 / 514 / 514 | 20 / 20 / 20 | 28 / 28 / 28 |

A06은 345열을 공동 비교에 보냈고 A11 전체 적용은 1,507열을 보냈다. 이 패널에서 채점은 같았다. Rollup/Drilldown도 같은 집계였다. 자동 별칭을 포함한 A07 결합은 Selection에서 최종 선택되지 않았으나 홀드아웃에서 A15와 정답 수가 같고 오추천이 7건 적었다. A05와 A07 주변 열의 정밀도는 98.97%, 98.40%였고 정확 추천율은 각각 32.68%, 36.60%였다.

방법별 임곗값 효과를 분리하기 위해 최종 정책의 0.64와 -0.10을 모든 방법에 동일하게 적용했다. 아래 수치는 이미 동결한 정책을 해석하는 소거 실험이다.

| 동일 임곗값 적용 | 정답 | 오추천 |
| --- | ---: | ---: |
| 자동 별칭 제외 A18 | 510 | 27 |
| 자동 별칭 허용 | 521 | 32 |
| 형식 특징 제외, Hard 검증 유지 | 474 | 37 |
| 결합 + 공동 비교 선택 적용 / 전체 적용 | 521 / 521 | 32 / 33 |
| 결합 + 역할군 상향·하향 판정 | 521 | 32 |
| 결합 + 강한 증거 후보 1개 확장 | 525 | 32 |
| 결합 + Top-1 / Top-5 / 전체 | 467 / 525 / 525 | 32 / 32 / 32 |

공통 임계에서 별칭은 정답 11개와 오류 5개를 추가했다. 형식 특징 제거 후 정답 36개를 잃고 오류가 10개 늘었다. 결합 정책에 공동 비교나 역할군 단계를 추가해도 정답 수는 같았다.

### 보류 복원과 실패 분석

| 지표 | A02 Phase 5 | A18 고정 조합 |
| --- | ---: | ---: |
| 직접 추천율 | 29.02% | 43.40% |
| 추천 정밀도 | 83.37% | 94.97% |
| 전체 오추천율 | 3.92% | 1.56% |
| HOLD 정답 거절률 | 97.15% | 98.40% |
| 최종 Top-3 정답 포함 | 366 | 510 |
| 보류 열, 그중 직접 매핑 정답 | 1,327 / 782 | 1,199 / 647 |
| 맞힌 필수 역할 / 881 | 264 | 384 |
| 문서당 수동 검토·수정 열 | 4.25 | 3.37 |

기존 HOLD에서 **155정답과 22오추천**을 추가했다. 이전 정답 341개 중 340개를 보전했고 이전 오류 15개를 정답으로 바꿨다. 기존 오추천 63건을 제거해 순 정답 +169, 순 오추천 -41이다. 문서군 bootstrap 1,000회에서 전체 열 기준 정답 비율 차이의 95% 구간은 +6.18~+12.56%p, 오추천 차이는 -3.58~-0.98%p였다. 완전 일치 문서가 Phase 5보다 8개 늘었고 Exact/RapidFuzz보다 4개 적었다.

새 정책의 비정답 665열의 첫 실패는 **신뢰도 376, 후보 검색 138, 충돌·공동 판정 66, 순위 55, 역할 30**이었다. 원시 HGB Top-1/3/5에 각각 880/1,037/1,147개가 있었다. 이 패널의 Top-3 검색 상한은 88.26%이며, Top-5에서는 97.62%다. 더 넓은 후보를 넣은 A08·Top-5는 최종 정답을 4건 늘렸다.

의미 정답은 1,200열 중 547열이었다. 변환 전 역할이 맞는 열 25개 중 20개를 **TRANSFORM_REQUIRED**로 식별했고 등록 후보로 넘긴 변환 열은 0개였다. 실제 데이터 등록은 시험 범위 밖이다. 전체 오추천 27건은 BOM 손실 비율을 `qty_per`로 판정한 18건과 금액·구매·반품 열을 `safety_stock_qty`로 판정한 4·4·1건이다. BOM의 대표 헤더는 `Proportion lost from component usage`다.

**기존 Phase 5 패널 회귀.** 557정답·6오추천을 재현했다. 기존 정답 HOLD 482건 중 신뢰도 450, 원시 Top-3 누락 12, 순위 10, 중복·범위 10이었다. 같은 파일에서 Phase 6은 603정답·0오추천, 정답 HOLD 442개, 완전 문서 41→56이었다. 기존 오류 유형을 재현한 패널이며 신규 패널의 성능과 구분한다.

## Risk–coverage와 신뢰도

Selection의 정밀도 하한별 위험과 추천 범위는 아래와 같다. 정밀도 98% 조건에서 정답이 가장 많았던 정책은 HOLD 목표에 미달했다. 정밀도·오추천·HOLD 세 제약을 적용한 최대 정답 373/643 정책의 공통 임계는 0.64, 마진은 -0.10이었다. 근소한 순위 차이는 허용하더라도 절대 적합성과 Hard 검증은 적용했다.

| 정밀도 하한 | 정확 추천 / 643 | 전체 추천 / 944 | 전체 오추천율 | HOLD 정답 거절률 |
| --- | ---: | ---: | ---: | ---: |
| 95% | 500 (77.76%) | 514 (54.45%) | 1.48% | 96.01% |
| 98% | 410 (63.76%) | 417 (44.17%) | 0.74% | 97.67% |
| 99% | 352 (54.74%) | 352 (37.29%) | 0% | 100% |

| 별도 Risk 110문서 진단 | 결과 |
| --- | --- |
| 업무 영역·필드별 임계 | 영역 478정답/7오추천, 필드 470/9. 최종 동결 정책에는 미포함 |
| 절대 적합성 Brier/ECE | 원시 0.1079/0.1883, logistic 0.0572/0.0530, isotonic 0.0700/0.0470 |
| 문서군의 단조 오류 발생 손실 CRC | 40개 군 최소 보정 위험 1/41=2.44%. 1% 인증 불가. 5%에서는 임계 0.76, 오류군 1, 보정치 4.88% |
| 문서군 최악 누락의 split conformal | 컷오프 1.0. 홀드아웃 1,736열에 모든 필드와 HOLD가 포함되어 직접 singleton 0 |

CRC는 동결 추천을 임곗값으로 제외할 때의 단조 손실을 대상으로 했다. 분모가 변하는 추천 정밀도와는 다른 양이다. 교환가능성을 새 회사의 분포에서 확인하지 못해 실제 위험 보장을 주장할 수 없다.

## Solar 캐시와 비용

A03/A04는 Phase 3 Final 130문서와 Confirmatory 100문서의 동일 입력 Mini 4/Pro 4 캐시를 검증했다. 신규 Holdout의 Solar 모델 응답과 새 Typed·Listwise·증거 조건의 실제 Solar 비교는 **NOT_RUN**이다.

| 기존 동일 입력 | Final 정답/오추천 | Confirmatory 정답/오추천 | Final USD / P50–P95 ms | Final 계약 영향 |
| --- | ---: | ---: | ---: | ---: |
| Mini 기본 | 583/45 | 383/57 | 0.02762793 / 1,139–3,314 | 50/130 |
| Pro 기본 | 607/37 | 407/41 | 0.07788000 / 2,688–4,844 | 26/130 |
| Mini 업무 지식 | 571/27 | 348/49 | 0.02893330 / 1,006–3,145 | 54/130 |
| Pro 업무 지식 | 611/36 | 424/31 | 0.08201457 / 2,520–4,849 | 33/130 |

각 방식에서 Final 130건과 Confirmatory 100건의 응답을 캐시로 재생했다. 신규 요청은 0건이다. 기록된 입력·출력 토큰과 문서당 비용은 다음과 같다.

| 방식 | Final 입력/출력 토큰 · USD/문서 | Confirmatory 입력/출력 토큰 · USD/문서 | Confirmatory P50–P95 ms · 계약 영향 |
| --- | ---: | ---: | ---: |
| Mini 기본 | 184,663/16,625 · 0.000213 | 161,209/12,905 · 0.000234 | 993–2,394 · 55/100 |
| Pro 기본 | 177,008/14,748 · 0.000599 | 157,641/12,255 · 0.000682 | 2,824–5,220 · 42/100 |
| Mini 업무 지식 | 196,226/16,701 · 0.000223 | 174,006/14,781 · 0.000256 | 1,292–3,353 · 64/100 |
| Pro 업무 지식 | 189,829/14,675 · 0.000631 | 167,236/12,443 · 0.000716 | 2,903–4,562 · 39/100 |

A17은 같은 기존 파일에서 Phase 5 추천을 잠그고 Mini·Pro가 동의한 HOLD를 보완했다. Final은 239/19→486/24, Confirmatory는 250/7→353/12였다. 정답 손실 0건, 새 오추천 각각 5건이다. 신규 계약 영향률 1% 목표는 실호출 없이 측정할 수 없다. 응답의 잘림·ID·중복·부분 채택은 테스트 대역으로 검증했다. [Phase 3 원 실측과 계약 평가](MAPPING_FINAL_ARCHITECTURE_EVALUATION_20261124.md)

공급사 사용량 CSV가 확인되지 않아 계산액 USD 2.02422308와 미확정 예약 USD 7.88260000을 유지했다. 합계 **USD 9.90682308**, 남은 한도 **USD 0.09317692**다. 콘솔 세전 USD 1.65는 요청별 과금 증빙으로 사용하지 않았다. 신규 요청과 과금은 0이다. 새 Selection 10문서의 Typed Top-3 계획에서 모델별 출력 상한은 8,902토큰, 본문은 Mini/Pro 160,643/160,633바이트, 예약 상한은 USD 0.022150810/0.066449130이다. 이 수치는 공급사 실측 사용량과 별개다.

신규 GEPA(A13)·MIPROv2(A14)·Bootstrap 실험, 신규 프롬프트·합성 LM 별칭·반례, 순열 호출은 **NOT_RUN**이다. 비용 대조와 새 합성 입력의 전송 승인이 필요하다. 비교 시 MIPROv2는 지시문·예시를 탐색하고 GEPA는 실패 피드백으로 프롬프트를 수정한다. 동일 모델·개발 분리·호출 및 비용 상한을 적용하고, 요청·실패·평가·reflection 모두 공용 비용 보호 경로로 계량한다. 의미·과잉 HOLD·형식·중복·유형·계약 실패를 따로 채점해 정밀도 98%, 오추천율 1%, HOLD 98%를 만족하는 후보 중 정답 수가 가장 큰 후보를 고른다.

## 결론과 재현

근거가 가장 뚜렷한 후속 후보는 **고정 검색기, 원본 업무·형식 검증, 후보별 절대 신뢰도와 제한적 후보 확장**이다. 공동 비교와 역할군 상향·하향 판정의 추가 이득은 확인하지 못했다. 형식 조건 약화 없이 BOM 비율/수량 반례와 새 양식의 검색 실패부터 해결해야 한다. 새 양식의 정밀도 저하 때문에 운영 반영은 보류했다.

고정 로컬 정책의 문서당 프로파일·HGB 검색 P50/P95는 6.95/24.64 ms, 선택 판별 자체는 0.22/0.30 ms였다. 공통 특징을 미리 계산한 뒤의 비교는 typed 0.23/0.33 ms, 선택적 공동 비교 0.57/0.80 ms, pairwise 1.08/2.49 ms였다. 네트워크·모델 학습은 포함하지 않았다. 운영 추천·외부 호출 기본값과 승인 흐름은 그대로다.

주요 파일은 러너, 데이터 생성, 판별·순위, 위험 보정, 요청·응답 계약과 소거 실험으로 구성한다. [러너](../scripts/evaluate_mapping_phase6.py) · [데이터](../scripts/mapping_phase6_data.py) · [판별·순위](../scripts/mapping_phase6_rank.py) · [위험 보정](../scripts/mapping_phase6_risk.py) · [요청·응답 계약](../scripts/mapping_phase6_contract.py) · [동일 임계 소거 실험](../scripts/audit_mapping_phase6.py) · [테스트](../backend/tests/test_mapping_phase6.py)

```powershell
$env:PYTHONPATH='backend;.;scripts;.artifacts/mapping-research/deps;.artifacts/mapping-research/metrics-deps'
$env:PERSISTENCE='disabled'
$env:OMP_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='2'
$out='.artifacts/mapping-research/phase6/verified'
.\.venv\Scripts\python.exe scripts/mapping_phase6_data.py --output $out
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase6.py billing --output $out
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase6.py select --output $out
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase6.py holdout --output $out
.\.venv\Scripts\python.exe scripts/audit_mapping_phase6.py --output $out
.\.venv\Scripts\python.exe scripts/evaluate_mapping_phase6.py historical --output $out
.\.venv\Scripts\python.exe scripts/verify_upstage_backend_replay.py
.\.venv\Scripts\python.exe -m pytest --no-db -q --tb=short
```

Python 3.11, NumPy 2.4.6, SciPy 1.17.1, scikit-learn 1.9.1. 비DB **1,342 통과·68 건너뜀**, RapidFuzz 48·70건 및 Phase 3 캐시 회귀 통과. OpenAPI·JSON Schema를 재비교했고 변경 파일 보안 검사 발견은 0건이다. 실DB·Docker는 미실행이다. 생성 데이터·점수·학습 가중치는 Git 제외 경로에 둔다.
