# 정마나미·이희원 전달 — 데이터셋 컨텍스트

## 화면 담당

GET /datasets로 ID/이름/설명/source_type/status를 읽고 선택한다. GET /datasets/{id}는 상세, POST /datasets는 SYNTHETIC 데이터셋 생성이며 권한/인증 구현이 아니다. schema_name은 서버 내부 값으로 노출/입력하지 않는다.

배치 등록/목록/상세/재검증/승인/반려, 제품/자재/BOM/재고/수요/CAPA/Routing, 예측 생성/목록/상세, 계획 생성/목록/후보/검토/What-if/Excel의 **모든 요청**에 query dataset_id를 동일하게 보낸다. 누락은 TISSUE-LEGACY 호환 규칙이며 전체 자료를 뜻하지 않는다. multipart dataset_id를 함께 보내면 query와 같아야 한다. PlanCommand에 dataset_id를 명시했다면 query와 같아야 한다.

데이터셋 변경 시 선택 UUID·계획 후보·캐시·실행 이력·진행 중 응답을 데이터셋별로 분리한다. 타 데이터셋 UUID는 404/409로 처리하며 다른 데이터셋에서 자동 검색하지 않는다. DATASET_NOT_FOUND/INVALID/INACTIVE/EXISTS/MISMATCH 오류를 처리하고 실제 서버 실패를 Fixture 승인으로 대체하지 않는다. 이번 변경에서 frontend는 수정하지 않았다.

## 엔진 담당

계산 알고리즘·모듈 폴더는 변경하지 않았다. PlanningInput.dataset_id와 command.dataset_id는 필수 의미 정보이고 값이 같아야 한다. legacy DTO의 생략값은 TISSUE-LEGACY다. 새 실행 지문에는 데이터셋을 포함한다. Forecast의 input_digest는 기존 엔진 지문이고 dataset_input_digest는 백엔드 소속 지문이므로 서로 같다고 가정하지 않는다. What-if는 같은 데이터셋의 저장 부모 입력을 재사용한다.

CHUNGPAMO-2027의 공용 SAW1과 동시 LB1을 보존했다. 신원/접근 권한, 신규 계산 정책, 계획 엔진 성공·정식 승인은 이 격리 기능의 완료 범위가 아니다.
