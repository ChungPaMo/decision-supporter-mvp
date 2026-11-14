# 합성 CAPA·Routing 기준 시드

**SYNTHETIC / TISSUE-CAPACITY-BASE-01**. 고정값을 수기로 구성한 DB/API 통합 검증 자료다. 실제 기업 측정값·ERP 기본값·정식 계산 정답이 아니다.

- resources.csv: M1 포장 설비 1대, L1 인력 풀 2명.
- quantity_limits.csv: TP-10R, 2027-01, 10500 EA. EA=10롤 1팩.
- hours_budgets.csv: M1 정규 160 설비시간/잔업 20, L1 정규 **총 170인시**/잔업 20. 인력 수로 다시 곱하지 않는다.
- routing_steps.csv: RT-TP/V1/PACK, M1 60 EA당 1설비시간. 같은 공정의 resource_requirements JSON에 L1 1000 EA당 18인시를 보존한다.
- tissue_capacity_template.xlsx: 네 시트 전체 입력 양식. 승인용은 capacity_upload.xlsx(세 시트)와 routing_upload.xlsx(공정 시트)로 분리했다. 매크로·외부 연결 없이 생성한 고정 합성 템플릿이다.
- baseline.json: 전체 DTO·생성 근거. 시드는 CSV와 의미가 같은 고정 XLSX 두 파일을 승인한다. 재생성 시 ZIP 메타데이터로 SHA가 달라질 수 있어 무조건 재업로드하지 않는다.
- shared_equipment.json, reduced_hours.json, material_shortage.json, midmonth_version.json, invalid_unit.json, unapproved_resource.json 및 scenario_overlays.json: 추가 합성 시나리오. 기본 시드에 삽입하지 않는다. 공유 설비는 TP-SECOND의 별도 제품 승인이 필요하다. 자재 부족 예시는 BOM/재고 overlay이며 실제 자재 코드를 확인하고 독립 fixture로 구성한다. 기존 승인 재고를 덮어쓰지 않는다. invalid/unknown 예시는 승인 거부용이다.

기존 tissue_products/materials/bom/inventory/demand.csv를 먼저 승인한다. capacity에는 자원→가용시간이 한 배치로 들어가고 routing은 그 자원을 참조한다. 단독 CSV도 해당 entity로 업로드 가능하다. 빈 선택값은 null이며 predecessor_step_ids와 resource_requirements는 JSON 문자열이다.

등록: 저장소 루트에서 `.venv/Scripts/python.exe scripts/seed_tissue_capacity.py`. 전용 55433 개발 DB와 동일 SHA만 재사용하며 다른 자료가 발견되면 중단한다. DB 초기화는 하지 않는다.

스키마·참조·API·미정 정책은 [데이터 사전](../../../docs/CAPACITY_ROUTING_DATA_DICTIONARY.md)을 따른다. 엔진 계산 공식은 이 자료에서 결정하지 않는다.
