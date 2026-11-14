// Hand-authored synthetic PPT cases. No optimizer, MRP or what-if calculation is implemented here.
export const DEMO_PLANS = [
  { name: '기준형', qty: '9,000', capacity: '월 총량 예시', material: '롤 5,000개 부족', stock: '1,000팩', basis: 'P50 설명 사례', usage: ['9000', '150', '162'], shortage: ['5000', '0', '0'], required: ['90000', '9000', '900'] },
  { name: '안정형', qty: '11,000', capacity: '한도 초과 예시', material: '롤·필름·박스 부족', stock: '1,000팩', basis: 'P80 설명 사례', usage: ['11000', '183.3333', '198'], shortage: ['25000', '1500', '100'], required: ['110000', '11000', '1100'] },
  { name: '비용절감형', qty: '8,000', capacity: '월 총량 예시', material: '필수 자재 충분 예시', stock: '0팩', basis: 'P50 설명 사례', usage: ['8000', '133.3333', '144'], shortage: ['0', '0', '0'], required: ['80000', '8000', '800'] },
] as const;
export const DEMO_RESOURCES = [
  { label: '월 생산수량', resource: 'TP-10R', limit: '10500', unit: '팩' },
  { label: '포장 설비', resource: 'M1', limit: '180', unit: '설비시간' },
  { label: '작업 인력', resource: 'L1', limit: '190', unit: '인시' },
] as const;
export const DEMO_MATERIALS = [
  { id: 'TP-ROLL', name: '휴지 롤', available: '85000', coefficient: '10롤/팩' },
  { id: 'TP-FILM', name: '포장필름', available: '9500', coefficient: '1장/팩' },
  { id: 'TP-BOX', name: '외박스', available: '1000', coefficient: '0.1개/팩' },
] as const;
