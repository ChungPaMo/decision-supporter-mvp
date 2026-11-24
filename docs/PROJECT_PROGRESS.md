# 충파모 프로젝트 진행상황

2026-11-24 (KST), 메인 Windows PC. 김대영이 [`c4cb3c5`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/c4cb3c519e4dc205f2e74f1f2196b0fbd91a75f4)에서 전용 회귀 DB 0009의 P1 단일 테스트를 완료했다. BASE/WHAT_IF가 각각 201·200·상세 조회를 통과했고, 저장 부모의 SAW1 80시간 What-if에서 안정형 결품 3,612→1,437, 생산량 96,583→97,791 EA였다. SQL 실패 롤백·다른 데이터셋 부모 404·정식 승인 501과 개발 DB 지문 보존을 확인했다. P2의 C02 승인 원장·SQL reader·`0010` 코드는 작성했고 공식 입고 수치는 비DB 실제 엔진에서 확인했다. `0009→0010` 회귀 적용 및 합성 PO 실제 승인·조회는 별도 실행 승인 대기다. [P1 결과·P2 검증 범위](PLANNING_POSTGRESQL_INTEGRATION_VERIFICATION_20261124.md)

2026-11-24 (KST), 메인 Windows PC. 김대영이 [`91927a0`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/91927a0d568962526c896de518e4d3a01cd7b0ec)에서 개발 PostgreSQL의 승인 예측으로 공식 3개월 입력 진단과 실제 계획 Preview를 읽기 전용 검증했다. 두 API 모두 200, 생산 81행·자재 81행·제약 306개, 계획 이력 0→0, 개발 DB 지문 일치다. `RECEIPT_SOURCE_UNAVAILABLE`로 1월 MR-N3 가용량은 공식 입고 포함 대비 10,000 kg 적었다. SQL 스냅샷 분리 계산에서 안정형 결품 3,612→1,437 EA를 확인했다. 실제 부모를 사용하는 저장 검증은 전용 회귀 DB의 P1 쓰기 승인 대기다. C02 신규 migration 및 승인 입고 reader 설계를 기록했다. AI 매핑 Phase 9 실측은 보류다. [실DB 검증과 승인 범위](PLANNING_POSTGRESQL_INTEGRATION_VERIFICATION_20261124.md)

2026-11-24 (KST), 메인 Windows PC. 김대영이 기준 `main` [`5dec94b`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5dec94b2232550dfcb1346bb2f5ece225d643e9f)에서 Phase 9 Selection 50·Risk 50·Holdout 200문서를 분리하고 공용 누적 한도 USD 20의 연구 경로를 준비했다. Selection의 Phase 6은 147/326정답·0오추천·323HOLD였다. 신규 Solar 150회·USD 0.27052850 예약 상한의 정확한 전송 계획은 별도 승인 대기다. 비DB 1,359 통과·68 건너뜀, 기존 Solar 캐시 230문서 재생, 신규 유료 호출 0건. [Phase 9 계획·로컬 실측](MAPPING_SOLAR_ADVANCED_OPTIMIZATION_20261124.md)

2026-11-24 (KST), 메인 Windows PC. 김대영이 기준 `main` [`45de512`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/45de512b4a25395f605947c18c9c950ef9f085a8)에서 Phase 8 Solar 비교를 승인 범위 안에서 실행했다. 고정 Development 합성 BOM·재고에서 3모델×5방식의 신규 요청 30건이 모두 응답했다. Mini 4·Pro 4 직접 방식은 각각 21정답·0오추천·4HOLD로 같은 문서의 Phase 5·6에 필적했다. 신규 USD 0.01385329는 응답 토큰 기준 로컬 계산액이다. 누적 계산·예약 USD 9.92067637, 잔액 USD 0.07932363. 비DB 1,350 통과·68 건너뜀. 신규 양식의 중복 대상·과다 HOLD와 옵티마이저가 다음 연구 대상이다. [Phase 8 실측과 후속 계획](MAPPING_SOLAR_PHASE8_20261124.md)

2026-11-24 (KST), 보조 PC. 김대영이 기준 `main` [`df06bf0`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/df06bf01c94738196abc11c649af663fbdeb8871)에서 논문 기반 LLM 판별과 공식 DSPy·GEPA 연구 경로를 추가했다. 실제 Qwen Pointwise는 Selection 2문서에서 16/18정답·0오추천, 별도로 고정한 신규 6문서에서는 3/27정답·3오추천·계약 영향 2/6이었다. 같은 신규 6문서 Phase 6은 5정답·2오추천이었다. Solar 스모크 예약 추정 USD 0.059609, 합성 입력 전송 및 비용 승인 대기. [Phase 7 연구 보고서](MAPPING_LLM_PAPER_OPTIMIZATION_20261124.md)

2026-11-24 (KST), 보조 PC. 김대영이 기준 `main` [`cf4603d`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/cf4603d6b7ebb707f8d32d13d7e2798c9468e5f4)에서 Phase 6 논문 기반 오프라인 판별을 검증했다. 신규 합성 200문서에서 Phase 5 대비 341→510정답, 68→27오추천, 정밀도 94.97%, HOLD 정답 거절 98.40%였다. 정확 추천율 43.40%와 오추천율 1.56%는 적용 목표에 미달했다. 신규 신뢰도 보류 376열, 검색 누락 138열이 주요 병목이다. 비DB 1,342 통과·68 건너뜀, 신규 Upstage 호출 0건. 비용 계산·예약 합계 USD 9.90682308 유지. [논문·소거 실험·독립 평가](MAPPING_RESEARCH_PAPER_BENCHMARK_20261124.md)

2026-11-24 (KST), 보조 PC. 김대영이 [`24d3993`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/24d3993c18ee91bd256417fd9a638a29b3189786)에서 Phase 5 오프라인 컬럼 판별을 검증했다. 신규 합성 홀드아웃 180문서에서 정답 557/1,045(53.30%), 정밀도 98.93%, 오추천 6/1,536(0.39%), HOLD 정답 거절 491/491이었다. 새 오추천 6건은 가용재고를 할당재고로 분류한 사례다. 형식·업무·충돌 보호와 BM25 2개 예시 조합을 연구 후보로 유지한다. 비DB 1,333 통과·68 건너뜀, 신규 Upstage 호출 0건. 미확정 예약 USD 7.88260000이 포함된 계산·예약 합계 USD 9.90682308을 유지했다. [오류 분석·검증 보고서](MAPPING_ACCURACY_OPTIMIZATION_20261124.md)

2026-11-24 (KST), 보조 PC. 김대영이 [`84de5b0`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/84de5b06293e468b109a4f6f241d3142f86175a5)에서 Upstage Provider 6종과 선택형 Solar 컬럼 검토·문서 구조 API를 추가했다. 외부 기능은 기본 비활성화이며 합성 원본 SHA와 비용 예약을 요구한다. 기존 추천·저장·승인 경로를 유지한다. 비DB 1,313 통과·68 건너뜀, 캐시 230문서 재생 및 RapidFuzz 48·70건 회귀 통과. 추가 Upstage 요청 0건, 연구비 계산·예약 USD 9.90682308 유지. [연동·검증 보고서](UPSTAGE_BACKEND_INTEGRATION_20261124.md)

2026-11-24 (KST), 보조 PC. 매핑 Phase 3에서 승인된 Final 130문서와 Confirmatory 100문서를 실측했다. Final Mini 개념 형식 585정답·26오추천, Confirmatory Exact→RapidFuzz 286정답·0오추천, 같은 입력에 Solar HOLD 부분 채택 448정답·51오추천이었다. 기본 경로는 원본 파서와 별칭을 유지하고 Solar는 선택형 검토 후보로 판단했다. Parse Standard/Auto가 원본 범위 3/24를 연결했고 Extract Enhanced 원본 XLSX는 60초 응답 시간 초과였다. 누적 USD 10 중 계산·예약 USD 9.90682308. 비DB 1,264 통과·68 건너뜀. [최종 아키텍처 평가](MAPPING_FINAL_ARCHITECTURE_EVALUATION_20261124.md)

2026-11-24 (KST), 보조 PC. Phase 2에서 Upstage Solar·Embedding과 문서 분석을 공용 USD 5 원장으로 실측했다. 합성 텍스트 5표에서 Solar Pro 20정답·1오추천, 로컬 독립 100표에서는 정확 일치 280정답·0오추천이었다. 원본 XLSX 4개의 Parse 공통 비교에서 Standard/Auto 10/11표, 합성 PDF 12개의 Classify 10/12, 반복 행 Extract Enhanced 209/210값을 확인했다. BGE/Qwen 전체 문맥과 E5 최종 LayerNorm 학습을 검증했고 원본 셀·운영 매핑·승인 경로를 유지했다. 외부 130문서 전량 평가는 자동 승인 검토에서 보류됐다. [Phase 2](MAPPING_UPSTAGE_AND_FINAL_COMPARISON_20261124.md) · [문서 분석](MAPPING_UPSTAGE_DOCUMENT_INTELLIGENCE_20261124.md)

2026-11-24 (KST), 보조 PC. 시작 `main` [`560de30`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/560de30b20fb365e5e9e12aa229eac53c0dc912b)에서 김대영이 신규 합성 Train 8,539열·Calibration 703열·Final 1,132열(130문서)로 제조업 매핑을 비교했다. 문자열·통계·업무 지식 LightGBM은 474 정답·18 오추천·정밀도 96.34%·최종 Top-3 475/779. 전통 매칭, E5 소거/학습 투영층, BGE·Qwen 헤더, Reranker, 로컬 LLM, 전역 배정·이력을 분리 검증했다. 운영 교체·유료 API 호출·DB 작업은 후속 범위다. [종합 보고서](MAPPING_COMPREHENSIVE_RESEARCH_20261124.md)

최종 확인 **2026-11-24 (KST), 보조 PC**. 시작 `main` [`ec3a0d3`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/ec3a0d3)에서 김대영이 이희원 어댑터를 실제 BASE·WHAT_IF Preview/저장 서비스에 활성화했다. 공식 합성 2027-01~03의 독립 정답 **제약 306개·생산 81행·자재 81행** 일치. 입력 누락 전달, 월별 BOM·라우팅 선택, 입고 공급 상태, 메모리 저장 `201`·중복 `200`과 부모 지문을 검증했다. 전체 비DB **1,239 passed / 68 skipped**, Playwright 8개 통과. 실DB Preview·개발 DB 지문 비교·PostgreSQL 영구 저장은 이 PC에서 미실행이다. [판정·Docker PC 체크리스트](PLANNING_ENGINE_ACTIVATION_VERIFICATION_20261124.md)

최종 확인 **2026-11-23 (KST), 기존 개발 PC**. 김대영이 [`82fa99f`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/82fa99fd2018dee5e73072924e9c7280f7353cda)에서 로컬 CPU 컬럼 비교를 실행했다. 기존 48건 RapidFuzz·BGE를 재현하고 신규 합성 70건에 Qwen3-0.6B·BGE-M3·multilingual-E5-small의 문맥 효과를 측정했다. Qwen 전체 문맥은 Top-3 29/37·오추천 8/70, RapidFuzz는 6/37·7/70이다. 운영 추천은 RapidFuzz를 유지한다. Upstage 후속 비교용 입력 내보내기와 점수 채점 경로를 마련했다. 전체 비DB **1,220 passed / 0 failed / 67 skipped**. [CPU 비교 및 재현](MAPPING_LOCAL_EMBEDDING_EVALUATION_20261123.md)

직전 김대영이 [`1fee108`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/1fee1084385ebcbaccc2ce13f416649dd8279004)에서 별도 승인된 Edge→React→FastAPI→PostgreSQL 선택형 XLSX 쓰기 E2E **1회 실행 통과**를 확인했다. 제품·자재 승인 후 새 변환 `201`, 동일 입력 `200`, 이력·배치 재조회, 재검증·승인 버전 `1→2→3`, 신규 월수요 `0→1`과 화면 새로고침 후 유지까지 확인했다. 승인된 21개 테이블을 정리했고 개발 DB 지문은 모두 일치했다. HOLD→변환의 파일·범위 이관은 정마나미 후속이다. [쓰기 E2E 보고서](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-실제-브라우저-쓰기-e2e)

직전 읽기 전용 브라우저 검증은 [`741b6dc`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/741b6dc4a7f80acd633b70ca01e2a0c0f3b3adff)와 계획 엔진 변경 반영 후 [`2adab58`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/2adab58debdce885f34cc0e93010f0f82b0359a2)에서 **시나리오 5개 통과**, TypeScript 통과였다. XLSX 유형 추천·HOLD, 범위·수동 열·미리보기 오류, 저장 요청 구성과 기존 승인 수요 498행을 확인했다. [읽기 전용 단계별 결과·담당 인계](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-실제-브라우저-읽기-전용-검증)

직전 PostgreSQL 동시성 재검증은 수정 커밋 [`872492b`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/872492bdd6fdb4f1005e4f1533716f58444be68a)에서 **1 passed / 0 failed / 0 skipped / 0 deselected**였다. 동일 입력 `201`/`200`, 서로 다른 선택의 동일 CSV 경합 `201`/`409 DUPLICATE_UPLOAD`, 무관한 SQL 오류 `500`, 롤백 뒤 고아 데이터 0행을 확인했다. 회귀 DB 정리는 완료했고 개발 DB 60개 테이블·735개 객체·660개 정의 지문은 같았다. [수정 후 실DB 재검증](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-수정-후-postgresql-동시성-재검증)

직전 오류 매핑 수정의 기준 `main`은 [`b9bf235`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/b9bf2357fd9f6c273ca0088b2307a4fa5709925c)이다. SQL 저장소가 `public`과 데이터셋 스키마의 활성 배치 중복을 드라이버 진단으로 구분하고, 다른 고유 제약·FK·CHECK·연결 오류의 처리를 유지하도록 수정했다. 집중 비DB **109 passed**, 전체 비DB **1,194 passed / 0 failed / 67 skipped**. 동일 입력 `201`/`200`, 저장·승인 및 OpenAPI 동기화 회귀를 포함한다. [오류 매핑과 재검증 범위](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-중복-오류-매핑-수정과-재검증-범위)

직전 실DB 동시성 검증의 기준 `main`은 [`c136793`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/c136793c8b974f8b9cd321bbbd9df98b99ba3597)이다. 두 연결로 동일 선택 `201`/`200` 재사용, 범위별 입력 지문, 변조 거부, 고유 제약과 롤백을 확인했다. 당시 서로 다른 범위가 같은 정규 CSV로 경합하면 DB가 중복을 막았고 API는 `500 PERSISTENCE_ERROR`를 반환했다. pytest는 **0 passed / 1 failed / 0 skipped / 0 deselected**였고 정리 후 회귀 DB 업무 데이터 0행, 개발 DB 지문 일치를 확인했다. [동시성 검증](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-postgresql-동시성무결성-검증)

직전 기존 개발 PC의 기준 `main`은 [`5507c0a`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5507c0ab98d95db0a6780b56fff7c8a1f327283f)이다. 김대영이 별도 회귀 DB에서 Alembic `0009`와 XLSX 선택 이력 SQL 테스트 **3 passed / 0 failed / 0 skipped / 0 deselected**를 확인했다. 실제 FastAPI·SQL에서 신규 저장 `201`, 재시도 `200`, 재조회 `200`, 선택 좌표·원본 SHA·지문 보존, 명시적 승인 전후 월수요 0→1행과 오류 시 롤백을 검증했다. 개발 DB의 60개 테이블·735개 객체 지문 및 기존 승인·예측 건수는 일치했다. 완료 커밋 제목은 `test: verify selected xlsx history on PostgreSQL`이다. [실DB 검증 결과](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-기존-개발-pc의-postgresql-검증-결과) · [나미님 인계](XLSX_SELECTION_PERSISTENCE_HANDOFF.md)

직전 보조 PC의 시작 `main`은 [`423c456`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/423c456cf11d090866293c0812c78d6cd7bb81e2)이다. 사용자 선택 XLSX를 기존 변환 이력과 승인 전 배치에 저장하고 같은 원본·정책·선택을 재현하도록 구현했다. TestClient·메모리에서 201 저장/200 재시도, 상세 조회, 재검증·명시적 승인, 데이터셋 격리와 중간 오류 롤백을 확인했다. 새 마이그레이션은 없다. 당시 전체 비DB **1,164 passed / 0 failed / 67 skipped**. [보조 PC 검증 결과](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#보조-pc에서-확인한-동작)

직전 11/23 범위 선택 작업에서 원본 SHA에 연결된 시트·헤더·데이터 범위를 구조 미리보기·분류·추천·프로파일·변환 미리보기에 적용했다. 기본 헤더 포착 18/200, 지정 헤더 200/200, 평면 BOM Top-3 0/27→9/27 및 전체 HOLD를 확인했다. 당시 비DB **1,128 passed / 0 failed / 66 skipped / 6 deselected**. 이번 저장 연동에서 200개 구조와 평면 BOM의 기존 결과를 재현했다. [범위 선택 검증](XLSX_TABLE_SELECTION_VERIFICATION_20261123.md)

직전 11/23 분류 계약 작업의 시작 `main`은 [`b2b3ecd`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/b2b3ecd7941b2e6b3cc706d95614d09a584f0115)이며 완료는 [`5002853`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/50028536a4af176306704be574409b142f10eaaf)이다.

현실형 합성 XLSX 200개를 읽어 실제 첫 표 헤더를 포착한 18개, 제목·병합·숨김·수식 동작을 확인했다. 문서 종류 분류 라벨은 200개 모두 일치했다. 평면 BOM 9개의 원본 매핑은 모두 HOLD였다. 표만 복사했을 때 27열 중 9열을 찾았고 숫자 열의 잘못된 단위 하위 후보 9건을 차단했다. 기존 승인 게이트 앞에 구조화 HOLD와 CAPA·Routing 등록 안내를 추가했다. [XLSX 검증과 인계](CLASSIFIER_XLSX_MAPPING_VERIFICATION_20261123.md)

11/23 전체 비DB pytest **1,115 passed / 0 failed / 66 skipped / 6 deselected**. OpenAPI/Schema 동기화와 승인 게이트 시험 통과. 보안 검사에서 이번 변경 파일 발견 0건, 기존 분류기 합성 샘플 관련 발견 201건이다.

11/22 기존 개발 PC의 컬럼 추천 비교 시작 `main`은 [`6e7056a`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/6e7056aeb09166b2bc82d994faaae47f5af15db9)이다. 완료 커밋은 `eval: compare local BGE-M3 and harden mapping suggestions`로 식별한다.

같은 합성 헤더 48건에서 로컬 BGE-M3를 새로 실행했다. RapidFuzz 보완 방식의 Top-3는 26/32→32/32, 오추천은 3/48→7/48이었다. 운영 API는 RapidFuzz를 유지하며 금액·출고·기준/가용 혼용의 수량 오추천을 차단한다. 전체 비DB pytest **1,114 passed / 0 failed / 66 skipped / 0 deselected**. 격리 PostgreSQL 승인 전 저장은 실제 SQL로 확인하고 롤백했다. 개발 DB는 강제 읽기 전용으로 보존했다. [새 비교와 검증](MAPPING_BGE_EVALUATION_20261122.md)

직전 통합 사전검증 시작 `main`은 [`5552b56`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5552b56dfce38a63f1fff1a45d6e76a0735772b7)이며 완료 커밋은 [`6e7056a`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/6e7056aeb09166b2bc82d994faaae47f5af15db9)이다.

제품 선택 순서에 따른 중복 실행을 방지하고, Preview와 신규 저장에 승인 입력 커버리지와 HARD 적용 상태 검증을 공통 적용했다. 실제 격리 PostgreSQL에서 TEST_DOUBLE 12개월 저장·재조회·계보·고유 제약·잠금·실패 롤백을 확인했다. 개발 DB는 읽기 전용으로 조회해 3개월 진단과 게이트를 확인하고 60개 테이블·735개 객체 지문을 보존했다. 전체 비DB pytest **1,109 passed / 0 failed / 66 skipped / 0 deselected**. `AVAILABLE=False`이며 실제 계획 엔진 영구 실행과 화면 연동은 후속이다. [사전검증·화면 API 인계](PLANNING_CONTRACT_V04_HANDOFF.md#2026-11-22-백엔드-통합-사전검증과-화면-연동)

직전 v0.4 계약 작업의 시작 `main`은 [`5c65cf3`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5c65cf38986fb1a5804f357bdb52efed33e2d650)이며 완료 커밋은 [`5552b56`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5552b56dfce38a63f1fff1a45d6e76a0735772b7)이다.

김대영이 C01 기간 1~12개월, C03 What-if 검증, C06 모순 판정 차단을 공통 계약과 기존 백엔드에 반영했다. C02는 승인 입고 DTO와 공급 검증 경계까지 구현했다. 개발 DB 0009에는 승인 입고 원장이 없어 실제 진단은 `RECEIPT_SOURCE_UNAVAILABLE`을 표시한다. 공식 데이터 3개월 스냅샷의 예측 27행·시간예산 18행·수량한도 3행을 실제 SQL로 검증했다. 비DB 전체 **1,102 passed / 0 failed / 66 skipped / 0 deselected**, TypeScript·Vite 빌드 통과. 개발 DB 전후 지문과 원본 SHA 일치. 계획 엔진의 팀 계약 변환부와 정식 승인 게이트 후속은 [v0.4 인계](PLANNING_CONTRACT_V04_HANDOFF.md)에 정리했다.

직전 이희원 작업 기록 **2026-11-22 (KST)**. 작업 시작 `main`은 [`d49818f`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/d49818f2d9038e31e52f6a95027005a91d97eb2a)다. 해당 변경은 `feat: planning what-if recalculation for three plans` Commit과 [누적 이력](DEVELOPMENT_CHANGELOG.md)으로 식별한다.

이번에는 이희원이 **What-if 재계산**(`what_if/core.py`: 수요 배수 전체·제품별, 자원·월 잔업 한도, 입고 예정 수량·취소 → 세 안 모두 재계산, 기준 결과와 비교)을 구현하고 충파모 시연 장면 3개를 [결과 요약](../modules/planning_engine/tests/chungpamo/RESULT.md)에 추가했다(예: 2월 절단기 특근 80h → 안정형 결품 3,612→1,437). 계산 코어·충파모 독립 정답 일치는 같은 날 `fbd6419`·`d49818f`. **팀 계약 `engine.planning.run`은 여전히 `AVAILABLE=False`**(C01~C03 확정 후 변환부 연결). 아래 11/18 이전 기록은 해당 시점 결과다.

2026-11-18 기준 김대영 작업: 시작 `main` [`231bcb2`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/231bcb262c98e764349fc54e5c3c6706e083f46f), `feat: diagnose approved planning inputs without running the engine`.

최종 확인 **2026-11-18 (KST), 보조 개발 PC**. 작업 시작 `main`은 [`231bcb2`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/231bcb262c98e764349fc54e5c3c6706e083f46f)다. 이번 변경은 `feat: diagnose approved planning inputs without running the engine` Commit과 [누적 이력의 마지막 항목](DEVELOPMENT_CHANGELOG.md)으로 식별한다.

이번 B01~B03에서 단일 월 `POST /planning-inputs/preview`, 공통 참조·출처·단위·기간 검증과 계약 협의 명세를 추가했다. **비DB pytest 978 passed / 0 failed / 66 skipped / 6 deselected**. 저장 경계는 대역이며 새 진단 경로의 실제 SQL 검증은 기존 개발 PC의 후속이다. [진단 검증·화면 인계](PLANNING_INPUT_DIAGNOSTICS_VERIFICATION.md)

11/17 기존 개발 PC에서 **집중 비DB pytest 71 passed**, 공식 3개 월 각각의 PlanningInput 실제 SQL 읽기 조립·미구현501을 확인했다. 개발 DB0009·60테이블/스키마 객체735개·승인7+9배치·예측각1건의 전후 보존도 확인했다. 이 기록은 신규 진단 API 구현 전의 결과다. [계획 통합 준비 보고서](PLANNING_ENGINE_INTEGRATION_READINESS.md)

11/17 실제 PostgreSQL 검증(`77067f1`)은 **전체 pytest 1015 passed / 0 failed / 0 skipped / 2 deselected**였다. 공식 원본→변환 이력·승인→예측의 실제 SQL 흐름을 확인했다. 별도 승인 후 개발 DB **0008→0009 적용 완료**. 기존55개 데이터 테이블·승인7+9배치·예측각1·기존객체/볼륨을 보존했고 새 이력4테이블은 빈 상태다. 이후 강제 읽기 전용 GET24건/60테이블 보존을 확인했다. [당시 상세](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md)

이 문서는 **최신 상태**, [DEVELOPMENT_CHANGELOG](DEVELOPMENT_CHANGELOG.md)는 **시간순 변경 이유·결과**, 개별 검증 보고서는 **상세 근거**, [AGENTS](../AGENTS.md)는 **매 작업의 읽기·갱신 규칙**이다. 이전 보고서의 “이번 작업”은 그 보고서 작성 당시를 뜻한다.

## 프로젝트 개요

가상 휴지 제조기업 충파모의 데이터 입력·검증·수요예측·생산계획 의사결정을 지원하는 MVP다. 추천과 사용자 최종 판단을 구분하며 자동 승인하지 않는다.

- 저장소: [ChungPaMo/decision-supporter-mvp](https://github.com/ChungPaMo/decision-supporter-mvp), `main` 직접 개발.
- 기술: Python 3.11+ / FastAPI / Pydantic / SQLAlchemy / Alembic / PostgreSQL 16, CSV·XLSX 파서(openpyxl), RapidFuzz. 예측은 단일 `engine/forecast` 구현(LightGBM), 화면은 React·TypeScript·Vite·Zustand. 검증은 pytest·TestClient·Playwright.
- 구조: `frontend/` → `backend/` API·검증·승인·저장 → `modules/` 분류/예측/계획 어댑터. `contracts/`가 공통 DTO·Schema·OpenAPI, `infrastructure/`가 DB 구성이다.
- 흐름: 파일 선택 → 분류/매핑 추천·사용자 확인 → 정제/변환 미리보기 → 승인 전 배치 → 명시적 검증·승인 → 승인 자료 기반 예측 → 계획 계산/검토(아직 엔진 연결 필요).

| 담당 | 책임·경로 |
| --- | --- |
| 김대영 | `backend/`, `contracts/`, `infrastructure/`, `tests/e2e/`, `scripts/`, `.github/`, 공통 문서·설정, API/DB/통합 |
| 이훤 | `modules/file_classifier/` — 업로드 규칙 분류 및 별도 문서 분류 연구 |
| 이희원 | `modules/planning_engine/` — 단일 예측 구현, 공식 합성 데이터, MPS/RCCP/MRP/What-if |
| 정마나미 | `frontend/` — 화면·상호작용·API 클라이언트·표시 타입 |

상세 경계는 [OWNERSHIP](OWNERSHIP.md), 입출력은 [INTEGRATION_CONTRACT](INTEGRATION_CONTRACT.md)를 따른다. 담당자 배정과 기능 완료는 별개다.

## 최신 개발 현황

| 기능 | 실제 구현·검증 수준 | 담당 | 남은 문제·근거 |
| --- | --- | --- | --- |
| 데이터 입력·파싱 | CSV/XLSX·7종 배치·수동 매핑·재검증·승인/반려 유지. 공식8마스터+원장 변환9번째 배치와 선택 XLSX 변환 이력을 실제 PostgreSQL로 검증 | 김대영 | 동시 저장 및 화면 전체 E2E는 별도. [공식 자료 검증](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) · [선택 XLSX 실DB 검증](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-기존-개발-pc의-postgresql-검증-결과) |
| 파일 자동 분류 | 업로드용 `rules-0.4.0`이 구조화 HOLD를 제공하고 백엔드는 CAPA·Routing 등록 힌트를 반환한다. 사용자 선택 범위로 재분류 가능 | 이훤(알고리즘), 김대영(API) | 화면 안내와 범위 선택 연계는 후속. [모듈 갱신](https://github.com/ChungPaMo/decision-supporter-mvp/commit/66880a5) · [표 선택](XLSX_TABLE_SELECTION_HANDOFF.md) |
| 컬럼 매핑·AI 후보 추천 | 정확 일치·별칭·수동 override·RapidFuzz Top-3와 기본 비활성 상태의 선택형 AI 검토 API를 유지한다. 연구 경로에서 Qwen 후보 판정과 Solar 3모델·5방식의 고정 합성 스모크를 실행했다. | 김대영 | 새 양식의 역할 혼동·중복 제안·과다 HOLD를 검증한다. 확대 Solar 비교와 유료 DSPy에는 새 전송·비용 승인이 필요하다. [Phase 8 실측](MAPPING_SOLAR_PHASE8_20261124.md) · [Phase 7 검증](MAPPING_LLM_PAPER_OPTIMIZATION_20261124.md) · [Upstage 연동](UPSTAGE_BACKEND_INTEGRATION_20261124.md) |
| 정제·변환 | 원본5파일86,214→498, SQL 이력·원본bytes/SHA·승인 전 batch 연결·재조회·동시201/200·실제DB 실패 rollback 검증 완료 | 김대영 | 회귀/개발DB0009 적용 확인. 개발DB는 기존공식자료 중복등록 없이 새이력0건 유지. SYNTHETIC_ONLY를 일반 기업에 자동 적용하지 않음. [이력 계약](INGESTION_INTEGRATION_HISTORY.md), [실DB 근거](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| PostgreSQL·데이터셋 격리 | 신규v2의 로컬FK·UUID격리·불변/지연트리거 실제 검증. 보관dataset 포함3스키마·기존81테이블 보존 probe 후 rollback. 개발0009도 별도승인·백업확인 후 적용 | 김대영 | 개발/회귀 현재0009. 기존자료와 연결된 볼륨은 보존, downgrade2개 미실행. dataset_id는 인증권한 아님. [최신 근거](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| 수요예측 | 단일 엔진/계약 유지. 실제 승인된 변환 수요498행→예측OK/27행 저장·재조회·P50≤P80≤P90, 미승인 probe 제외 확인 | 이희원(엔진), 김대영(API), 정마나미(화면) | 합성 회귀 결과를 실제 기업 적합성으로 일반화하지 않음. [이번 실DB 검증](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| 계획 입력 진단 | 승인 input을 한 트랜잭션에서 1~12개월 조립. CP 1·3개월과 LEGACY 1개월 실제 SQL 읽기 확인, 예측 범위 부족 409. 예정 입고 공급 미연결 표시 | 김대영(API), 정마나미(화면 연계) | 6·12개월 실제 조립에는 그 기간을 포함한 저장 예측이 필요. 화면에서 기간·진단·오류 표시 연계. [v0.4 인계](PLANNING_CONTRACT_V04_HANDOFF.md) |
| 생산계획·제약 계산 | **11/24 `AVAILABLE=True`**. 이희원 어댑터·MPS/RCCP/MRP/What-if 코어를 김대영이 Preview와 저장 API에 연결했다. 공식 합성 3개월의 제약 306개·생산/자재 각 81행, 1·3·6·12개월, 월 경계·중간 변경·중복, 공급 있음/빈 목록/null, BASE·WHAT_IF 실계산과 메모리 `201`/`200`을 확인했다. | 이희원(계산·변환), 김대영(계약·저장·예시) | 개발 PC에서 승인 데이터의 읽기 전용 Preview 및 전후 지문 비교, 별도 승인 후 전용 회귀 DB에서 영구 실행. 승인 입고 원장과 reader는 후속이며 정식 `APPROVE`는 501 유지. [활성화 및 실DB 인계](PLANNING_ENGINE_ACTIVATION_VERIFICATION_20261124.md) |
| 프론트엔드 | 데이터셋 선택·배치 등록/검토/재검증/승인·분류 패널·예측 조회 및 별도 DEMO 화면 구현. **2026-11-23:** 화면 요청 P0·P1 연결 — 원본 파일 공유와 명시적 "이 파일 등록", 등록 전 컬럼 분석·Top-3 후보·열 선택, 판매 원장 변환 정책/미리보기/이력 저장·배치 연결, 변환 이력 목록·상세, CAPA·Routing 7종 등록. `/ingest/*` dataset scope 적용. type-check/build 통과, 보조 PC 로컬 PostgreSQL(0009)에서 공식 자료로 브라우저 확인 | 정마나미 | **2026-11-23 추가:** XLSX 시트·표 범위 선택 UI(`/ingest/xlsx-layout`, `table_selection`/`table_selections`)와 `hold_kind`·`registration_hint` 안내 연결. 대시보드를 "지금 처리할 일" 목록 중심으로 재구성하고 예측·등록·계획 화면의 표시를 정리(표시만 변경, API 계약 변경 없음). 미연결: 계획 v0.4 화면. **`tests/e2e/browser`는 미실행이며 갱신 필요**(등록이 파일 선택 즉시가 아니라 "이 파일 등록" 클릭으로 바뀜, 데이터 종류 7단계). 기존 npm 취약점 2건 미검토. [API 인계](INGESTION_UI_API_HANDOFF.md), [화면 변경 요청](INGESTION_UI_CHANGE_REQUEST.md) |
| 전체 E2E | 공식14파일 SHA와 입력·저장·승인·예측 **TestClient+실제PostgreSQL** 경로 검증 완료. 메모리/SQL 대역으로 저장 성공을 대체하지 않음 | 김대영(통합), 각 담당 | 신규입력 전체브라우저·실제계획계산을 포함한 제조전체E2E는 미완료. [이번 범위](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |

## 현재까지의 핵심 성과

- 대표 자료는 이희원 담당 **CHUNGPAMO-2027 공식 합성 생성기(SEED=20261115)**의 기존 원본·정답이다. [원본/정답 14파일 SHA manifest](../contracts/examples/ingestion_e2e_source_manifest.json)를 대조하고 검증 전후 보존했다. 임의 성공 fixture로 대체하지 않았다.
- 제품·자재·BOM·재고·자원·CAPA·Routing의 실제 DTO 연결과 공유 설비/동시 인시 요구를 확인했다. 판매 거래 **86,214행 → 월별 수요 498행**이 독립 정답의 제품/월/Decimal 수량/단위와 일치했다. 정상 수요만 집계하고 취소 제외·반품 별도를 유지했다.
- 파일 분류기→컬럼 매핑 API, RapidFuzz Top-3 추천→사용자 확인, 변환 이력→승인 전 배치→명시적 승인 게이트를 연결했다. 추천·미리보기·이력 저장·업무 승인 상태는 서로 구분한다.
- 11/16 공식 자료 FastAPI TestClient E2E와 프론트엔드 연계 문서를 완료했다. 당시 **저장소와 CAPA SQL 경계는 메모리/테스트 대역**이었으며, 이후 11/17의 별도 실제 PostgreSQL 검증으로 입력·승인·예측 저장 경로를 확인했다. 실제 계획 계산 저장은 여전히 미검증이다.
- 가장 최근 실제 PostgreSQL 포함 전체 Python은 **2026-11-17: 1015 passed / 0 failed / 0 skipped / 2 deselected**. 기존 DB63개 중61개와 추가실DB3개를 통과했고 downgrade2개는 사용자 지시로 미실행이다. 당시 별도 비DB는951 passed/66 skipped. TypeScript/build·계약 동기화·보안도 통과했다. [11/17 상세](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md). 이전943/63skipped는 [11/16 기록](INGESTION_API_E2E_VERIFICATION_20261116.md)이다.
- 과거 실제 PostgreSQL 회귀 결과는 2026-11-15 `ff448ac`의 608 passed/0 skipped 등 해당 시점 보고서의 기록이다. 신규 0009나 현재 DB의 검증으로 승격하지 않는다. [DB 근거](DB_REGRESSION_E2E_VERIFICATION.md)

## 남은 작업

1. **김대영:** 개발0009 적용/기존자료 보존과 회귀DB의 원자성·불변성·동시성·격리·공식자료→승인→예측을 검증했다. 기존공식자료를 개발DB에 중복등록하지 않는다. 백업 실제복구리허설과 보존기간 정책은 후속이며 다음 파괴적 fixture도 새 범위승인이 필요하다.
2. **정마나미:** [화면 요청 P0/P1](INGESTION_UI_CHANGE_REQUEST.md)에 따라 기존 화면을 재사용해 신규 API를 연결한다. 기존 승인 UI를 중복 구현하지 않는다. 기존 npm 취약점 2건(Vite/esbuild)도 담당 영역에서 검토한다.
3. **김대영, 기존 개발 PC:** 공식 3개월 승인 데이터를 READ ONLY로 진단하고 실제 Preview와 전후 지문을 확인한다. 별도 승인 후 `chungpamo_regression`에서 BASE·WHAT_IF 저장·재사용과 격리를 검증한다. 승인 입고 영구 원장과 변경 이력은 별도 설계 및 DB 적용 승인이 필요하다. [실DB 체크리스트](PLANNING_ENGINE_ACTIVATION_VERIFICATION_20261124.md#docker-pc-인계)
4. **통합/화면 담당:** 공식 자료로 전체 계획 브라우저 E2E를 수행한다. LIVE Preview와 이력·저장·승인 상태를 구분한다. 정식 승인은 서버 인증과 승인 정책 확정 후 연결한다.
5. **김대영·화면 담당:** 별도 합성 파일 승인·인증·서비스 한도·비용 계량을 연결한 뒤 선택형 AI 검토의 실호출과 사용자 확인 UI를 검증한다. 프롬프트 품질은 별도 평가한다. 기업 데이터 검토는 단위·거래 상태·모호성·변환 정책부터 확인한다. [Upstage 연동 및 UI 인계](UPSTAGE_BACKEND_INTEGRATION_20261124.md)

## 개발 환경 제한

**11/24 엔진 활성화는 Docker·PostgreSQL이 없는 보조 PC에서 수행했다.** DB 접속·마이그레이션·DB 테스트·실DB Preview는 미실행이다. 기존 개발 PC 검증과 별도 승인된 0009 적용은 각각의 보고서에 기록된 결과다.

- 기존 DB 데이터를 보존한다. 개발 DB/기존 `chungpamo_test` 초기화 금지, 독립 회귀 DB의 파괴적 작업도 [개발 절차](DEVELOPMENT_WORKFLOW.md)의 식별·보존 확인·별도 실행 승인이 필요하다.
- `frontend/`, `modules/file_classifier/`, `modules/planning_engine/` 담당 폴더 제한과 신규 migration 추가 금지를 유지한다. 추천 점수 기반 자동 등록·승인, 원본 기업 데이터 외부 API 전송을 하지 않는다.
- 분류·컬럼 추천 변경은 TestClient와 비DB 회귀로 검증했다. 66개 DB 테스트와 Alembic 명령 호출 검사 6개는 미실행이다.

## 작업 재개와 팀 공유

작업 시작/완료 절차는 [AGENTS](../AGENTS.md)에 따른다. 시작 시 이 문서와 최근 [CHANGELOG](DEVELOPMENT_CHANGELOG.md), 최신 Git·실제 코드를 함께 확인하고, 종료 시 두 문서를 갱신해 변경 파일만 Commit·Push한다. 검증/기록/Push 실패도 남긴다.

팀 공유용 [Notion 인계 페이지](https://app.notion.com/p/41b441f66d7881f4a060e999510b694b)는 이번에 조회·수정·동기화하지 않았다. GitHub의 두 Markdown 파일이 기준 기록이다. 후속 동기화는 날짜·Commit·상태·근거 링크를 사용한다.
