"""Manufacturing column vocabulary shared by review and offline evaluation."""

DESCRIPTIONS = {
    'product_id': '완제품·판매상품을 식별하는 품목 코드 또는 SKU, finished product identifier',
    'product_name': '판매 제품의 이름·표시명, finished product name',
    'product_type': '완제품·반제품 등 제품의 분류, product type or category',
    'material_id': '원재료 또는 구매 자재를 식별하는 코드, raw material identifier',
    'material_name': '원자재 명칭, raw material name',
    'period': '제품 수요가 귀속되는 연월, monthly demand period YYYY-MM',
    'demand_qty': '판매 또는 고객 주문의 월별 필요 개수나 예상 소비 수량, monthly sales demand quantity, units needed',
    'base_unit': '제품 또는 자재의 기준 계량 기호, base unit of measure EA kg m BOX',
    'unit': '수량을 측정하는 단위 기호, unit of measure EA kg m BOX',
    'safety_stock_qty': '품절에 대비해 유지할 최소 비축 재고, minimum buffer safety stock quantity',
    'bom_id': '제품 구성표의 식별 번호, bill of materials identifier',
    'bom_version': '제품 구성의 개정 차수 및 버전, BOM revision',
    'status': '제품 구성표의 업무 승인 상태, approval lifecycle status',
    'is_active': '현재 사용하는 구성표인지 여부, active boolean flag',
    'valid_from': '해당 BOM 개정 적용이 시작되는 날짜, effective start date',
    'valid_to': '해당 BOM 개정 적용이 끝나는 날짜, effective end date',
    'base_qty': 'BOM 레시피에서 산출 수량 환산의 기준이 되는 모제품 개수, BOM reference output quantity',
    'line_no': '구성 항목 배열 순번, BOM line number',
    'component_type': '투입 구성품이 자재인지 반제품인지의 분류, component type',
    'component_id': '상위 제품에 투입되는 하위 구성품 코드, child component identifier',
    'qty_per': '모제품 한 기준 단위에 필요한 하위 재료의 투입 수량, component usage per parent unit',
    'scrap_rate': '재료 투입에서 예상 손실의 비율, expected scrap fraction',
    'item_type': '재고 대상이 제품인지 자재인지의 구분, stock item type',
    'item_id': '창고에서 재고를 관리하는 품목 식별 코드, stock item identifier',
    'as_of_date': '창고 재고 스냅샷 또는 실사 기준 날짜, stock snapshot date',
    'on_hand_qty': '창고가 물리적으로 보유한 전체 재고 수량, total physical on-hand stock',
    'allocated_qty': '특정 출고나 주문에 이미 예약 또는 배정된 재고 수량, reserved allocated stock',
    'available_qty': '물리 재고에서 예약을 제외하여 즉시 불출 가능한 수량, available unreserved stock',
}

REJECT = {
    'returns': '고객의 반품·반송·환불 접수나 회수 물량, returned or refunded units RMA',
    'production': '공장 작업 지시와 생산 실적의 제조 완료 수량이나 불량 건수, actual production output or scrap count',
    'purchase': '공급사에 발주한 구매 수량 또는 아직 입고되지 않은 구매 주문 잔량, supplier PO quantity or open receipts',
    'shipping': '송장에 따라 실제 발송·출고·배송 처리한 물량, physically shipped quantity',
    'money': '수량이 아닌 돈의 금액·단가·원가·매출·통화, monetary value price or sales amount',
    'unrelated': '업체·거래처·창고 등 별도 명칭, 비고 또는 의미를 알 수 없는 모호한 값, unrelated metadata or unknown',
}

BUSINESS_WORDS = {
    'demand_qty': '수요 필요 소요 주문 customer demand requirement requested consumption',
    'allocated_qty': '예약 배정 묶인 allocated reserved committed held',
    'available_qty': '가용 가능 잔여 free unreserved available',
    'on_hand_qty': '현재고 실물 보유 실사 total physical onhand tally',
    'qty_per': '투입 소모 소요 component usage ingredient factor',
    'base_qty': '기준 환산 산출 reference denominator output batch',
    'valid_from': '시작 개시 시행 첫날 start first opens begins',
    'valid_to': '종료 만료 폐지 마지막날 end last expires closes',
    'period': '귀속 연월 월간 월별 bucket monthly period month',
    'scrap_rate': '손실 폐기 비중 loss scrap fraction share waste',
}

CONFLICTS = {
    'demand_qty': '반품 반송 되돌려 환입 생산 공장실적 구매 발주 공급 출고 물류 return refund reverse production manufacture procurement supplier vendor shipment dispatched',
    'period': '주문일 접수 출고 배송 booked placed shipping submission',
    'on_hand_qty': '예약제외 unreserved free',
    'allocated_qty': '미할당 예약제외 unreserved free',
    'available_qty': '차감전 includingreserved physicaltotal',
}
