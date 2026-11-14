# Planning engine · 이희원

기존 예측 엔진은 `engine/forecast/` **한 벌**이다. `from engine.forecast import run`을 유지하며 루트 editable install로 import한다. `forecast/`를 새로 복제하지 않는다. 기존 계산식은 이관 중 바꾸지 않았다.

```powershell
./.venv/Scripts/python.exe -m pytest modules/planning_engine -q
```

MPS/RCCP/MRP/What-if 알고리즘은 미구현이다. 각 전용 폴더에서 개발하고 공유 진입점 `engine.planning.run(PlanningInput)`을 사용한다. 현재 진입점은 NotImplementedError다. AVAILABLE=True와 run을 구현하면 기존 API가 읽기 전용 어댑터를 통해 호출한다. 계획 저장·정식 승인이 켜지는 것은 아니다. 상세 입력/출력·fixture·완료 기준은 [TEAM_HANDOFF](../../docs/TEAM_HANDOFF.md)를 따른다.

DB/UI 접근 없이 DTO를 받아 반환한다. 스냅샷 생성·실제 forecast execution UUID 조회·실행 저장·승인·출력은 backend 소유다. 계약 변경은 docs/INTEGRATION_CONTRACT.md와 CAPA 질문을 통해 통합 담당에게 요청한다.
