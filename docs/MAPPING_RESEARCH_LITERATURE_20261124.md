# 스키마·컬럼 매핑 선행 연구

2026-11-24 조사. 논문의 과제·분모가 충파모의 제조업 `허용 표준 필드 또는 HOLD`와 다르므로 발표 수치를 그대로 비교하지 않았다. 공개 코드와 라이선스는 확인한 출처를 명시했다. 구현체가 확인되지 않은 행은 논문의 아이디어를 참고했다.

| 연구·구현 | 연구 대상과 활용 가능한 설계 | 출처·실행 경계 |
| --- | --- | --- |
| Matchmaker, ICML 2025 | 의료 스키마에서 후보 생성·정제·확신도 결합 및 합성 시범 사례. 후보 회수와 최종 적합성 평가를 분리하는 근거 | [PMLR 논문 및 보충 자료](https://proceedings.mlr.press/v267/seedat25a.html). 저자 LLM 실험 미재현 |
| Magneto, VLDB 2025 | 대규모 의료·생물의학 속성에 소형 후보 생성과 LLM 판별. 이 프로젝트에서는 합성 데이터와 작은 head부터 비교 | [논문](https://arxiv.org/abs/2412.08194) · [Apache-2.0 구현/실행 의존성](https://github.com/VIDA-NYU/magneto-matcher) |
| ConStruM, 2026 v3 | 구조 문맥과 혼동 필드의 대비, 후보별 의사결정. 의미가 비슷한 수요·생산·발주와 BOM 기준수량·투입량에 적용 가능 | [개정 논문·저자 코드 링크](https://arxiv.org/abs/2601.20482). 해당 버전은 SIGMOD 2027 게재 승인 표기 |
| SemStruct, KDD 2026 | 동결 언어 임베딩과 열·행·값의 그래프. Valentine, SOTAB-SM에서 평가. 재고 산식 확신을 추가 근거로 사용하는 설계에 참고 | [IBM Research](https://research.ibm.com/publications/semstruct-contextualizing-semantic-embeddings-with-structural-information-for-schema-matching) · [논문](https://arxiv.org/abs/2605.30729). 별도 GNN 학습 미실행 |
| ZTab, ICDE 2026 | 도메인 기반 합성 데이터로 고정 후보군에 주석을 붙이는 zero-shot annotation. 문서 생성부터 역할을 정의하는 방식에 참고 | [저자 코드·실행 안내](https://github.com/hoseinzadeehsan/ZTab). 재사용 라이선스는 추가 확인 필요 |
| LLMATCH, 2025 | LLM을 사용해 여러 종류의 스키마 매핑을 한 프레임워크에서 처리. 고정 대상에 전체 스키마 입력과 제한 후보 입력을 비교하는 근거 | [저자 프리프린트](https://arxiv.org/abs/2507.10897). 실행 가능한 저자 구현·라이선스 미확인 |
| TabEmb, ACL 2026 | 구조와 의미를 공통 임베딩으로 묶어 열 유형·열 간 속성·테이블을 주석 처리. 주변 열과 테이블 제목의 역할을 독립 측정 | [ACL 논문](https://aclanthology.org/2026.acl-long.757/) · [저자 코드·데이터](https://github.com/hoseinzadeehsan/TabEmb). 직접 실행 미수행 |
| RODEO, ICDE 2026 | 언어 모델+GNN과 온라인 hard-negative mining으로 CTA/CPA를 라벨 제약 매칭으로 바꿈. 혼동 역할을 세분화하는 데 참고 | [저자 코드·학습 명령](https://github.com/dtai-kg/RODEO). SOTAB용 그래프·학습 환경이 필요해 직접 미실행 |
| ReMatch, 2024 | 대상 스키마를 검색한 뒤 LLM이 판별. 속성명·설명 중심이며 원본 DB 행 접근 없이 비교. 내용이 불투명한 제조 헤더에는 소수 합성 값과 형식 근거 추가 검토 | [저자 프리프린트](https://arxiv.org/abs/2403.01567). 동일 이름의 멀티모달 ReMatch와 다른 연구 |
| SchemaML, 2026 | schema.org 평가에서 임베딩과 Random Forest 쌍 판별을 연결. 임베딩 없는 분류기와 같은 데이터에서 비교할 근거 | [IEEE 논문](https://ieeexplore.ieee.org/abstract/document/11632351/). 공개 실행 패키지 미확인 |
| RF4SM / ALMa | RF4SM은 후보 쌍 RF 판별, 네트워크 제약, 사용자 피드백을 비교. ALMa는 언어·구조 매처 결합에 active learning으로 사용자 확인 사례를 고름 | [RF4SM 저자 논문 및 ALMa 원전 참고문헌](https://link.springer.com/article/10.1186/s13173-021-00119-5). 저자 모델 직접 미실행 |
| Valentine, ICDE 2021 및 패키지 1.x | 맞는 값이 있는 경우와 의미만 같을 때 결과를 분리. COMA 이름/인스턴스, Cupid 구조, Similarity Flooding 그래프, DistributionBased 값 분포, Jaccard 집합 비교 | [원전·알고리즘](https://github.com/delftdata/valentine/blob/master/docs/research.md) · [매처·실행 API](https://github.com/delftdata/valentine/blob/master/docs/matchers.md) · [라이선스](https://github.com/delftdata/valentine). 설치한 1.0.1의 실제 결과는 보고서에 별도 기록 |
| Sherlock / Sato | Sherlock은 값 통계·문자 분포·임베딩으로 의미 유형을 예측한다. Sato는 표 수준 문맥과 열 유형을 결합한다. 범용 의미 유형의 분류 결과를 제조업 필드 매핑 성능으로 전용하지 않음 | [Sherlock 논문·코드](https://sherlock.media.mit.edu/) · [Sato 저자 코드](https://github.com/megagonlabs/sato) |
| Data Harmonization Benchmark / WDC SMB | NYU 벤치마크는 스키마와 값 변환을, WDC는 SOTAB-SM·T2D-SM에 고정 분할을 제공. 공개 과제는 한국 제조 역할과 다른 독립 외부 확인용 | [NYU 데이터·실행법](https://github.com/VIDA-NYU/data-harmonization-benchmark) · [WDC 다운로드·과제](https://webdatacommons.org/structureddata/smb/). 리소스별 사용권 검토 후 사용 |
| 2025–2026 후속 | BDIViz의 사람이 검증하는 도구, SINT-Flow의 다단계 검토, MetaHarmonizer의 공개 데이터 오염 대조. 합성 평가만으로 현장 정밀도를 주장하지 않는 근거 | [BDIViz](https://arxiv.org/abs/2604.10763) · [SINT-Flow](https://arxiv.org/abs/2607.24492) · [MetaHarmonizer 프리프린트](https://www.biorxiv.org/content/10.64898/2026.06.13.732088v1.full) |

## 상용 서비스 공개 기능

| 서비스 | 공개된 흐름과 적용 아이디어 |
| --- | --- |
| Flatfile | 시트를 선택하고 표준 필드 대응을 확인한다. 이전 사용자·동료의 선택과 ML을 사용하며 매핑 후 Review로 진행한다. 독립 정확도 비교에는 공급사 홍보 수치를 사용하지 않았다. [공식 도움말](https://support.flatfile.com/articles/8569925090-mapping-data) |
| OneSchema | `exact`, `fuzzy`, `historical` 조합 이후 미매핑 열에 AI 제안을 표시한다. 템플릿과 유효성 검사 및 최종 확인을 분리한다. [공식 AI 가이드](https://docs.oneschema.co/docs/ai-bundle) · [검증 안내](https://docs.oneschema.co/docs/validating-and-importing) |
| Dromo | 헤더와 일부 값으로 AI 제안을 만들고 사용자 확인·수정과 `autoMapHeaders` 기반 반복 업로드 활용을 공개한다. 충파모는 데이터셋·스키마 버전·표 구조별로 이력 재사용 경계를 실험했다. [공식 서비스 설명](https://try.dromo.io/blog/improving-data-import-accuracy-with-dromos-ai-powered-column-matching) |

세 서비스의 내부 모델 세부 파라미터나 승인 이력 충돌 우선순위는 공개 설명으로 확인되지 않았다. 이 연구의 상용 비교 범위는 사용자 흐름과 공개 기능이다.
