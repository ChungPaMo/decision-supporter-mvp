# CAPA·Routing 실제 등록 검증 — 2026-11-15

## 환경·안전

실행 전 main이 원격과 일치하고 작업 트리가 깨끗함을 확인한 뒤 시작했다. Docker Engine 29.4.0, 프로젝트 chungpamo-monorepo, 컨테이너 chungpamo-monorepo-db, 볼륨 chungpamo-monorepo-pgdata, 네트워크 chungpamo-monorepo-net, 호스트 바인딩 127.0.0.1:55433을 inspect로 확인했다. 접속 DB는 chungpamo, current_user는 chungpamo_app였다. 기존 개발 DB public 테이블은 0개였다.

개발 DB에 기존 0001~0005와 새 0006을 순차 적용해 현재 revision은 **0006**이다. 이전 migration 원문은 변경하지 않았다. 초기화/TRUNCATE/기존 업무 데이터 DELETE는 수행하지 않았다. 55432·sisicallcall 및 테스트 DB에는 접속하지 않았다. Docker 자원 변경, PoC/출처 저장소 변경, frontend/알고리즘 소유 폴더 변경도 하지 않았다.

## 실제 등록·승인 결과

기존 승인 API를 통해 아래 기준 시드를 등록했다. 모든 source_type은 SYNTHETIC, version은 2, 상태는 APPROVED다.

| entity | batch_id | approved_record_count |
|---|---|---|
| product | 61aefca9-8077-4ffe-95d0-722e2092fed1 | 1 |
| material | 2a09449b-3056-4862-83e1-740ef7f3867f | 3 |
| bom | c94f3a01-89cb-41e8-82ef-d94e7136b065 | 3 |
| inventory | 2764fdc3-c216-4e9e-a15e-62abc1ab925a | 4 |
| monthly_demand | e56c08b0-f078-41f0-9a4b-7f1f9c75a708 | 24 |
| capacity | 9beec28d-b963-415c-a43f-c66eb1175618 | 5 |
| routing | 1985c611-75a9-41d7-a3d6-ae6f94d6d1f3 | 1 |

실제 SELECT 행 수: production_resource=2, production_quantity_limit=1, production_hours_budget=2, production_routing=1, production_routing_step=1, production_routing_resource_requirement=2.

제품은 TP-10R(EA=10롤 1팩), 자원은 M1/L1, 가용시간은 각각 정규 160설비시간/170총인시와 잔업 20, 월수량 한도는 2027-01의 10500 EA다. PACK 한 공정에 M1·L1 소요를 별도 행으로 저장했다. 기준값과 양식은 [합성 자료](../contracts/examples/tissue_capacity/README.md), 실제 컬럼은 [데이터 사전](CAPACITY_ROUTING_DATA_DICTIONARY.md)에 있다.

시드 스크립트를 동일 파일로 재실행해 같은 batch_id·version·count를 재사용했고 중복 행이 생기지 않았다. API 조회는 `/capacity` 5행, `/routings` 1행이었다. 직접 SQL로 승인 상태를 조작해 시드하지 않았다.

## 실행 검증

- 전체 **비DB pytest 479 passed / 0 failed / 55 skipped**. 신규 등록/계약 시험 15개 포함. Starlette/httpx deprecation warning 1건.
- TypeScript `npm run type-check`, Vite `npm run build` 통과. frontend 파일은 변경하지 않았다.
- OpenAPI·공통 Schema를 생성 스크립트로 갱신했고 동기화 시험 통과.
- `scripts/verify_capacity.py`의 실제 PostgreSQL 비파괴 검증 **8개 항목 통과 / 0 실패**: 실제 저장 예측→승인 CAPA/Routing 입력, 미승인 업무행 제외, 원자 승인, 경쟁 배치의 409와 상태 보존, 승인 중 오류 rollback, late write/append-only 차단, 승인 트랜잭션 내부 CHECK(23514)/FK(23503), 두 연결 advisory lock 배타성.
- 오류 탐침 배치/업무 행은 바깥 트랜잭션 rollback 후 남지 않음을 SELECT로 확인했다. 검증은 합성 승인 수요로 예측 실행 한 건을 생성/재사용했으며, PlanningInput의 반복 조회·모델 버전·배치 출처를 보존했다. 전체 스냅샷은 로컬 ignored `.artifacts/capacity_snapshot.json`에만 보관한다.
- 보안 검사 findings=0. 신규 합성 XLSX 3개만 정확한 파일명·SHA-256으로 허용하며 다른 XLSX/비밀정보 차단 규칙을 유지했다.

**미실행:** public 스키마 초기화가 필요한 기존 DB pytest 55개, 파괴적 migration downgrade/왕복, PostgreSQL 브라우저 E2E, 두 HTTP 승인 요청을 동시에 시작하는 완전한 병렬 경합 E2E. 두 세션 잠금 검증과 순차 경쟁 배치 검증을 전체 병렬 E2E 통과로 표현하지 않는다.

## 발견·수정 및 후속

신규 entity 응답 DTO 누락, migration chain/entity 정적 검사, API 안내/OpenAPI 불일치를 수정했다. 기존 테스트 삭제·skip 전환은 없었다. 0006은 신규 파일이며 적용 후 SQL 의미 변경 없이 표기만 정리했다. 신규 entity API 및 동시 요구량 입력을 안내하는 [팀원 변경 요청](CAPACITY_ROUTING_CHANGE_REQUESTS.md)을 작성했고 담당자 알고리즘·화면은 수정하지 않았다.

셋업·대체자원·달력은 현재 참조값을 등록 오류로 처리한다. 월중 버전은 모두 보존하고 미확인 조건을 남긴다. MPS/RCCP/MRP/What-if 계산, CAPA 등록 UI, 계획 저장·정식 승인은 미구현이며 기존 501을 유지한다. 운영/정식 계산 데이터로 검증했다는 의미가 아니다.
