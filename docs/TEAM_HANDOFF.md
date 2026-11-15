# 팀원 전달 — 전체 E2E 개발 경계

> **데이터셋 후속 전달:** [데이터셋 계약](DATASET_ISOLATION.md)과 [화면 변경 요청](DATASET_FRONTEND_CHANGE_REQUEST.md)을 따른다. 희원: PlanningInput.dataset_id와 command.dataset_id가 같아야 하며 원본 batch/forecast/What-if는 같은 데이터셋이다. 공용 자원은 데이터셋 내부에서 공유한다. 마나미: 모든 DB API에 선택 dataset_id를 전송하고 선택 변경 시 다른 데이터셋의 배치/예측/계획 선택을 재사용하지 않는다. 이번 작업에서는 담당자 알고리즘·frontend 파일을 수정하지 않았다.

> **2026-11-15 계획 저장 기반:** 새 [계획 실행 계약](PLAN_EXECUTION_PERSISTENCE.md)을 확인한다. 희원: PlanningInput/Output과 engine.planning.run은 유지했으며 새 알고리즘은 구현하지 않았다. What-if는 저장 입력·부모 결과·안전한 command.overrides를 전달하고 적용 공식은 미확정이다. 마나미: Preview(`/plans`)와 영구 실행(`/plan-executions`)을 구별하고 조회/검토/반려를 연결한다. APPROVE 501과 미승인 export 차단을 성공으로 표시하지 않는다. 서버 상태/version/digest를 사용하며 테스트 대역을 실제 계산으로 표시하지 않는다. 양쪽 담당 폴더는 이번에 수정하지 않았다. 아래 초기 계획 저장 미구현 설명은 이전 상태이며 계산/인증/정식 승인 미구현은 여전히 적용된다.

> **2026-11-15 후속 통합:** CAPA/Routing 등록·승인·조회와 SQL provider의 승인 스냅샷 연결을 구현했다. 아래 최초 뼈대의 ‘CAPA 저장 미구현/null만 전달’은 과거 상태다. 현재 절차는 [데이터 사전](CAPACITY_ROUTING_DATA_DICTIONARY.md), 팀원 후속 요청은 [변경 요청](CAPACITY_ROUTING_CHANGE_REQUESTS.md)을 따른다. RoutingStep.resource_requirements는 동일 공정의 추가 동시 소요이며 순차 공정이 아니다. 모듈 폴더와 frontend는 수정하지 않았고, 계획 계산·계획 저장·정식 승인은 계속 미구현이다.

이관 기준: feature/backend-integration / af5e4fd에서 시작한 최종 뼈대 작업. 이후 개발 기준은 이 모노레포의 `main`이다. 이 문서는 알고리즘 구현 완료가 아닌 **각자 자기 폴더에서 시작할 수 있는 연결 지침**이다. 공통 API·DTO·DB 변경은 김대영과 검토한다. 실제 GitHub 로그인 미확인 때문에 CODEOWNERS 활성 규칙은 없다.

## 함께 사용하는 구조와 규칙

frontend → API/어댑터 → 승인 스냅샷 provider → 순수 모듈 → 타입 검증된 읽기 전용 응답. 등록·승인·예측의 기존 실API는 유지한다. 분류 결과는 추천이며 승인되지 않는다. 계획 preview도 persisted=false/approval_available=false다.

- 공통 import: contracts.interfaces.modules. 구체 모델은 base.py, capacity.py, planning.py로 분리했으나 기존 import를 재수출한다.
- 기존 /classifications, /plans, /plans/what-if 유지. 분류 파일 입력용 /classifications/file 추가.
- 모듈 내부는 app/SQLAlchemy/psycopg/UI를 import하지 않는다. source_manifest/실제 UUID를 서버가 구성한다.
- source repo 3개, 공통 migration 0001~0005, .env/비밀/기존 DB는 수정·복사하지 않는다.
- fixture의 `_note`를 읽고 `payload`를 파싱한다. TEST-DOUBLE-ONLY/합성 UUID는 실제 승인·운영 검증의 증거가 아니다.
- `main`의 원격 최신 변경을 확인·Pull한 뒤 담당 폴더에서 작업한다. 공유 변경이 필요하면 입출력 예시·버전/호환 영향·시험 결과를 김대영에게 요청한다. 다른 팀원의 폴더를 조용히 고치지 않는다.

## 이훤 — 파일 분류

**수정 영역**: modules/file_classifier/src/file_classifier/, modules/file_classifier/tests/. 자기 모듈 AVAILABLE 플래그와 classify 함수만으로 서버 경로에 연결한다.

**함수**: classify(ClassificationInput) → ClassificationOutput. 입력은 filename/sha256/format/sheets(columns/sample_rows)다. CSV 시트명은 null. 파일 bytes·DB 연결은 전달되지 않는다. /classifications/file은 같은 DTO를 만들고 JSON /classifications도 그대로 지원한다.

**출력**: recommended_entity 또는 null, 유일한 후보별 entity/score/reasons, hold, 전체 reasons, module_version. 점수는 [0,1], 임계값은 직접 합의·검증한다. HOLD에는 근거가 필요하다. 자동 승인·원본 DB 저장은 하지 않는다.

**독립 시험**:

```powershell
./.venv/Scripts/python.exe -m pytest modules/file_classifier -q
```

공통 fixture: classification_input.json / classification_hold.json / classification_ready.json. 실제 성능용 표본과 오분류·HOLD 임계값 시험은 자기 tests/fixtures에 익명·합성 자료로 추가한다. XLSX 시트 구조·중복 헤더·빈 시트·샘플 행 없음·혼합 유형·알 수 없는 파일을 포함한다. 분류 함수는 같은 입력의 재현성과 모델 버전을 추적해야 한다.

**완료 기준**: 독립 정확도/불명확성 근거, DTO 출력 검사, 미지원/예외 처리, JSON/파일 API 호출 계약, HOLD/추천 후 사용자 확인, 승인 gate 비우회 시험 통과. 미구현은 NotImplementedError(501), 예상하지 못한 예외/잘못된 출력은 MODULE_ERROR(500)로 경계에서 처리한다.

**수정 금지**: backend API·DB·승인 상태·contracts·frontend 공통 타입·루트 설정. entity=capacity/routing은 아직 현재 batch 계약에 없으므로 임의 추천 유형으로 추가하지 않는다.

## 이희원 — 예측·MPS/RCCP/MRP/What-if

**수정 영역**: modules/planning_engine/. 예측은 engine/forecast 한 벌만 유지한다. mps/, rccp/, mrp/, what_if/는 import 가능한 전용 패키지로 등록했다. backend 이동이나 별도 예측 복제 없이 engine/planning.py에서 이 패키지들을 호출할 수 있다.

**함수**: engine.planning.run(PlanningInput) → PlanningOutput. 준비되면 자기 모듈 AVAILABLE=True로 바꾸고 run을 구현한다. 현재는 False/NotImplementedError이며 알고리즘은 작성하지 않았다.

**입력**: command(실제 forecast UUID/제품/월/기준일/시나리오), forecast 지문·선택 rows, 승인 제품/자재/BOM/재고/출처 DTO, CAPA·라우팅 스냅샷 또는 null, 정책과 missing_inputs, What-if 기준 계획 snapshot. DB/UI 접근 없이 입력만 처리한다. missing/null을 0/무제한/기본 설비로 바꾸지 않는다.

**출력**: 2~3개 후보, 후보별 제품/월/수량/단위/feasibility/정책 근거/미확인, 수량·인시·설비시간·자재의 개별 평가, 자재 소요/가용/부족, 근거·경고·오류·module_version. 계산 불가 상태에는 성공 후보를 넣지 않는다. 성공 2~3개, 중복/범위/단위/참조/명백히 불완전한 FEASIBLE은 어댑터가 검사한다. 세 후보를 억지로 성공시키거나 계산식을 Fixture에 맞추지 않는다.

**독립 시험**:

```powershell
./.venv/Scripts/python.exe -m pytest modules/planning_engine -q
```

공통 fixture: planning_input.json / planning_output.json / capacity_registration.json. planning_output은 테스트 대역이며 실제 계산 정답이 아니다. PPT 합성 기준형 9000/안정형 11000/비용형 8000도 업무 공식 확정안이 아니다. 실제 검증에는 자기 tests/fixtures의 독립 손계산 정답·공유 설비 2제품·공정 선후·자재 부족·무해/결측/미지원 반례를 추가한다.

**완료 기준**: H-/N- 정책 결정 기록, 독립 계산 결과와 단위·오차 근거, 부하/자재 기여 내역·참조 보존, 예측 지문/모델 버전 추적, 지원 범위/불가능/미확인 구분, PURE 함수 시험·백엔드 계약 시험 통과.

**현재 한계**: 기본 provider는 승인 CAPA·라우팅이 없어 missing_inputs를 전달한다. 이런 입력은 UNVERIFIED/UNSUPPORTED 등으로 명시해야 하며 정책을 새로 발명하지 않는다. What-if는 저장된 기준 계획이 필요하지만 계획 저장소는 아직 없어 운영 provider가 501을 반환한다. 주입 provider로 확인한 호출 계약은 실제 저장 기능의 대체가 아니다.

**수정 금지**: backend DB/마이그레이션/승인·contracts·frontend·루트 packaging. 새 패키지 의존성이나 DTO 필드가 필요하면 김대영에게 공유 변경을 요청한다.

## 정마나미 — React 전체 화면

**수정 영역**: frontend/src/{screens,components,layouts,styles,services,types,store}/ 및 frontend 자체 설정. 현재 네이비/블루 PPT 스타일을 유지하고 공통 backend 계산을 브라우저에서 복제하지 않는다.

**주요 파일**:

- DataUploadScreen + ClassificationPanel: 파일 추천 요청·샘플 동의·HOLD·사용자 유형 선택 후 기존 등록·매핑·재검증·승인 API.
- ForecastScreen + ForecastChart: 실제 UUID 이력·조건·P50/P80/P90·제외/경고·DB 복원 유지.
- PlanningWorkspace: 5개 계획 하위 단계, 합성 설명/실제 연결 모드, 선택 지속·What-if 입력·최종 검토·DEMO Excel 안내.
- LivePlanningPanel: 실제 예측 ID·제품·월 선택, API 읽기 전용 응답, 단계별 결과/근거, 오류 시 DEMO로 전환하지 않음.
- UsageMeter: 서버 또는 **명시적 고정 합성** 사용량/한도 시각화. 비율 표시가 제약 계산·판정의 대체가 아님.
- services/planningDemo.ts: 수기로 작성한 합성 UI fixture. api.ts/types/modules.ts는 공통 계약의 화면 경계다.

**독립 시험**:

```powershell
cd frontend
npm run type-check
npm run build
npm run test:e2e:ui
```

브라우저 spec/서버 실행기는 김대영 소유 tests/e2e에 있다. 수정 요청과 화면 수용 기준을 전달한다. 성공 렌더러 시험은 TEST-DOUBLE-ONLY 응답을 주입한 것이며 실제 알고리즘 완료로 보고하지 않는다.

**완료 기준**: 7단계 이동·모바일·키보드/모달·실제 차트/표, 선택과 서버 상태의 분리, HOLD와 승인 gate, 409/422/501/503/네트워크 오류, 실제/DEMO 혼동 방지. Live preview는 메모리 상태일 뿐 서버 계획 저장·새로고침 복원이 아니다. 저장된 예측·배치 복원은 기존 실API를 사용한다.

**수정 금지**: backend DB/마이그레이션·엔진 계산·공통 계약/루트 테스트/CI. UI용 타입 확장은 가능하지만 서버 계약을 다른 의미로 바꾸면 안 된다.

## 김대영 — 승인 데이터·어댑터·공통 검증

**수정 영역**: backend/, contracts/, infrastructure/, tests/e2e/, scripts/, .github/·루트 공통 설정. 모듈의 알고리즘을 대신 작성하지 않고 승인 gate·버전·snapshot·트랜잭션을 관리한다.

**핵심 파일/후속 함수**:

- api/integrations.py, integrations/modules.py: JSON/파일 분류 어댑터와 공통 오류.
- integrations/planning.py: PlanningSourceProvider.load, SqlPlanningSourceProvider.load, execute. 현재 SQL은 읽기 전용이며 저장하지 않는다.
- CAPA 등록: CAPACITY_REGISTRATION_PLAN의 entity/승인 단위·참조·기간·precision을 확정하고 미래 신규 migration/API/provider를 구현한다.
- 계획 저장: 실행/계보/상태·모듈/정책/입력 지문·결과 원자 저장, 승인/정식 출력 조건 확정, What-if의 실제 기준 계획 provider를 구현한다. 기존 0001~0005 재작성 금지.

**검증 명령**:

```powershell
./scripts/check.ps1
./.venv/Scripts/python.exe -m pytest backend/tests/test_planning_adapter.py backend/tests/test_planning_sources.py backend/tests/test_module_integration.py -q --no-db
./.venv/Scripts/python.exe tests/e2e/run_ui_e2e.py
./.venv/Scripts/python.exe scripts/security_check.py
```

계약 수정 시 backend에서 export_contract_schema.py / generate_api_examples.py 실행 후 동기화 테스트를 통과시킨다. DB 테스트는 이번 단계에서 실행하지 않으며, 신규 provider와 미래 CAPA/계획 저장의 실제 PostgreSQL 검증은 별도 승인·전용 55433 테스트 DB 식별이 필요하다. 과거 490/12 결과를 이번 작업의 통과 수로 재사용하지 않는다.

## 변경 전달·검토 최소 항목

담당 경로·문제/변경 동작·입출력 예시·fixture의 합성/실제 구분·실행 명령과 passed/failed/skipped·미지원 범위·정책 결정 번호·공통 파일 변경 요청·데이터/비밀 제외 확인을 적는다. 폴더 소유권은 협업 규칙이지 GitHub의 경로별 접근 권한이 아니다. DEVELOPMENT_WORKFLOW.md에 따라 `main`에서 직접 테스트·Commit·Push하며 새 브랜치·PR은 생성하지 않는다. 강제 Push와 다른 팀원 변경 덮어쓰기는 금지한다.
