# 팀원 후속 변경 요청 — CAPA/Routing

## 이희원: modules/planning_engine/

공통 DTO의 기존 PlanningInput/CapacityRegistrationDraft 필드는 유지했다. RoutingStep에 기본 빈 배열 `resource_requirements: list[ResourceRequirement]`를 추가했다. 주 자원의 기존 resource_id/reference_qty/quantity_unit/run_time/time_unit/time_basis 등은 그대로다. 추가 배열은 **같은 공정에 동시 투입되는 다른 자원**이며 선행/후행 공정이 아니다. 주 자원을 배열에 중복 넣으면 거부한다.

합성 PACK: M1=60 EA당 1설비시간, L1=1000 EA당 18인시. 기계시간+인시를 합산해 공정 경과시간으로 해석하지 않는다. 셋업·대체설비·시간 기준 변환·공유자원 배분·목적함수는 여전히 H-/N- 결정 대상이다. 현재 provider는 승인된 스냅샷과 원본 배치 version/SHA/digest를 제공한다. 월중 버전은 모두 전달하며 미확인 사유를 남긴다.

요청: 새 배열을 독립 자원 부하로 읽는 모듈 수용 시험을 자기 폴더에서 추가하고, 계산 공식은 정책 합의 후 구현한다. 이 작업에서는 engine.planning.run이나 모듈 tests를 수정하지 않았다. 예제는 contracts/examples/tissue_capacity/baseline.json과 각 시나리오 JSON이다. 테스트 대역과 실제 계산 결과를 구별한다.

## 정마나미: frontend/

요청: `capacity|routing` 배치 유형, 고정 시트 양식/CSV, 새 CapacityRecordOut(section/payload/location/review_required), 조회 `/capacity|/routings`를 화면·표시 타입에 반영한다. 기존 5종 승인/예측 실API를 유지한다. 전체 양식의 routing을 capacity로 묵시 승인하지 말고 두 원자 승인 배치로 안내한다.

버전/digest·409·422·501·503 및 HOLD/오류 후 새 파일 또는 명시적 헤더 매핑 재검증을 그대로 적용한다. 코드 계산식·자동 승인·Fixture fallback을 추가하지 않는다. 계획 API는 아직 계산 모듈 501이며 실제 정식 승인/Excel과 연결된 것처럼 표시하지 않는다. 이번 작업에서는 frontend를 수정하지 않았다.

## 김대영: 공통 계약·서비스

제품별 필터·리비전 교체·공정/달력/셋업 마스터, 권한 정책·계획 저장·정식 승인·출력은 후속 범위다. 0006 등록 규칙은 계산 정책 확정이 아니다. 보안 검사의 XLSX 예외는 명시적 합성 템플릿 3개의 SHA-256에 한정했다. 템플릿 변경 시 합성 내용·외부 링크/매크로 여부와 기존 시드 충돌을 확인하고 허용 해시를 함께 검토한다. 테스트 DB 초기화 승인은 별도다.
