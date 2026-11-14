# 파일 소유권

| 담당 | 소유 경로 | 수정 경계 |
|---|---|---|
| 김대영 | backend/, contracts/, infrastructure/, tests/e2e/, scripts/, .github/, 루트 설정 | 공통 API·계약·승인 게이트·실행/CI 통합 |
| 이훤 | modules/file_classifier/ | 분류 알고리즘·모듈 테스트. DB 직접 쓰기·승인·공통 API 변경 금지 |
| 이희원 | modules/planning_engine/ | 예측 한 벌·MPS/RCCP/MRP/What-if·독립 계산 시험. DB/UI 의존 금지 |
| 정마나미 | frontend/ | 화면·스타일·상호작용·API 클라이언트·표시 타입. DB/마이그레이션/계산 로직 변경 금지 |

초기 통합에서는 김대영의 통합 작업으로 모든 영역의 경로와 연결을 조정했다. 이후 담당 폴더 밖 변경이 필요하면 API·입출력 예시·호환 영향과 함께 담당자에게 명세 변경을 요청한다. 공통 계약을 모듈 내부에서 조용히 복제하지 않는다.

`modules/planning_engine/engine/forecast/`가 예측 코드의 유일한 위치다. 별도 `forecast/` 복제품을 만들지 않는다. backend/app/models.py 및 sql_repository.py는 기존 위치를 유지했다.

실제 GitHub 로그인과 담당자 매핑이 확인되지 않아 `.github/CODEOWNERS`에는 활성 소유자 규칙을 넣지 않았다. 확인 후 김대영 검토로 등록하고 PR 보호 설정을 별도로 결정한다. 파일 소유권은 협업 규칙이며 GitHub에서 폴더별 쓰기를 자동 제한하지 않는다.

최종 뼈대의 함수·계약·fixture·독립 시험·금지 공통 파일·완료 기준은 [TEAM_HANDOFF](TEAM_HANDOFF.md)에 팀원별로 정리했다. `mps/rccp/mrp/what_if` 전용 패키지는 공통 packaging에 등록했으므로 담당자가 자기 폴더에 구현을 추가할 수 있다. API/스키마 생성물과 루트 E2E는 통합 담당이 관리하며 팀원이 생성물만 따로 수정하지 않는다.
