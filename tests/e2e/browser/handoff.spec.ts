import { test, expect, Page } from '@playwright/test';
import inputFixture from '../../../contracts/examples/integration/planning_input.json';
import outputFixture from '../../../contracts/examples/integration/planning_output.json';
import holdFixture from '../../../contracts/examples/integration/classification_hold.json';
import readyFixture from '../../../contracts/examples/integration/classification_ready.json';

const ID = inputFixture.payload.command.forecast_execution_id;
const forecast = { execution_id: ID, status: 'OK', input_digest: 'sha256:' + 'c'.repeat(64), dedup_key: 'd'.repeat(64),
  parameters: { trained_until: '2026-12-31', horizon_months: 1, p50_method: 'MA12', min_history_months: 12, random_seed: 42 },
  runtime_identity: {}, quantile_model_version: 'TEST-DOUBLE-ONLY', input_row_count: 24, forecast_count: 1,
  created_at: '2026-12-31T00:00:00Z', finished_at: '2026-12-31T00:00:01Z', input_batches: [], failure: null,
  result: { contract_version: 'forecast-output-0.1-draft', request_id: ID, status: 'OK',
    run: { run_id: 'FRUN-TEST', engine: 'forecast', p50_method: 'MA12', quantile_model_version: 'TEST-DOUBLE-ONLY', trained_until: '2026-12-31', horizon_months: 1, random_seed: 42, input_digest: 'sha256:' + 'c'.repeat(64), generated_at: '2026-12-31T00:00:01Z', data_classification: 'SYNTHETIC' },
    forecasts: [{ product_id: 'TP-10R', target_month: '2027-01', p50: '10000', p80: '12000', p90: '13500', horizon: 1, p50_method: 'MA12', quantile_model_version: 'TEST-DOUBLE-ONLY', trained_until: '2026-12-31' }], skipped: [], warnings: [], errors: [], adjustments: [] } };

async function savedForecastDouble(page: Page) {
  await page.route(/\/forecasts(?:\?.*)?$/, route => route.fulfill({ json: { items: [forecast], total: 1, limit: 20, offset: 0 } }));
  await page.route(new RegExp(`/forecasts/${ID}(?:\\?.*)?$`), route => route.fulfill({ json: forecast }));
  await page.goto('/');
  await page.getByRole('button', { name: /생산계획 비교/ }).click();
  await page.getByRole('button', { name: '실제 모듈 연결', exact: true }).click();
  await page.getByLabel('계획 입력 예측 실행', { exact: true }).selectOption(ID);
  await expect(page.getByRole('button', { name: '읽기 전용 계획 계산 요청' })).toBeEnabled();
}

test('actual classifier holds ambiguous input without creating a batch', async ({ page }) => {
  let writes = 0;
  page.on('request', r => { if (r.method() === 'POST' && /\/batches(?:\?|$)/.test(r.url())) writes++; });
  await page.goto('/');
  await page.getByRole('button', { name: /데이터 업로드/ }).click();
  const panel = page.getByRole('region', { name: '파일 유형 자동 분류' });
  await panel.getByLabel('분류할 파일 (CSV/XLSX)', { exact: true }).setInputFiles({ name: 'synthetic.csv', mimeType: 'text/csv', buffer: Buffer.from('product_id,qty\nTP-10R,10\n') });
  await panel.getByRole('button', { name: '파일 유형 추천 요청' }).click();
  await expect(panel.getByText(/HOLD —/)).toBeVisible();
  await expect(panel.getByRole('button', { name: '검토한 추천 유형 선택' })).toBeDisabled();
  await expect(panel.getByRole('table')).toContainText('rules-');
  expect(writes).toBe(0);
});

test('classification HOLD and reviewed entity selection never create a batch', async ({ page }) => {
  let writes = 0;
  page.on('request', r => { if (r.method() === 'POST' && /\/batches(?:\?|$)/.test(r.url())) writes++; });
  await page.route('**/classifications/file', route => route.fulfill({ json: holdFixture.payload }));
  await page.goto('/');
  const panel = page.getByRole('region', { name: '파일 유형 자동 분류' });
  await panel.getByLabel('분류할 파일 (CSV/XLSX)', { exact: true }).setInputFiles({ name: 'synthetic.csv', mimeType: 'text/csv', buffer: Buffer.from('a,b\n1,2\n') });
  await panel.getByRole('button', { name: '파일 유형 추천 요청' }).click();
  await expect(panel.getByText(/HOLD —/)).toBeVisible();
  await expect(panel.getByRole('button', { name: '검토한 추천 유형 선택' })).toBeDisabled();
  await page.route('**/classifications/file', route => route.fulfill({ json: readyFixture.payload }));
  await panel.getByRole('button', { name: '파일 유형 추천 요청' }).click();
  await panel.getByRole('button', { name: '검토한 추천 유형 선택' }).click();
  await expect(page.getByRole('complementary', { name: '데이터 종류' }).getByRole('button', { name: /^월별 수요/ })).toHaveAttribute('aria-current', 'true');
  expect(writes).toBe(0);
});

test('actual planning 501 never switches back to synthetic results', async ({ page }) => {
  await savedForecastDouble(page);
  await page.getByRole('button', { name: '읽기 전용 계획 계산 요청' }).click();
  await expect(page.getByRole('region', { name: '실제 계획 모듈 연결' }).getByRole('alert')).toContainText('MODULE_NOT_IMPLEMENTED');
  await expect(page.getByRole('region', { name: '서버 계획 미리보기' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '실제 모듈 연결', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText(/DEMO \/ UNVERIFIED —/)).toHaveCount(0);
});

test('typed test-double module output renders across steps but never enables approval', async ({ page }) => {
  await savedForecastDouble(page);
  await page.route(/\/plans(?:\?.*)?$/, route => route.fulfill({ json: {
    contract_version: 'planning-preview-0.2-draft', forecast_execution_id: ID, input_digest: 'sha256:' + 'e'.repeat(64),
    result: { ...outputFixture.payload, contract_version: 'planning-handoff-0.2-draft' }, persisted: false, approval_available: false,
  } }));
  await page.getByRole('button', { name: '읽기 전용 계획 계산 요청' }).click();
  await expect(page.getByRole('region', { name: '서버 계획 미리보기' })).toContainText('TEST-DOUBLE-ONLY');
  await page.getByRole('button', { name: 'RCCP 능력 검토', exact: true }).click();
  await expect(page.getByRole('region', { name: '서버 계획 미리보기' })).toContainText('미산출');
  await page.getByRole('button', { name: '최종 MPS', exact: true }).click();
  await expect(page.getByRole('button', { name: '최종 MPS 승인 (저장 기능 미연결)' })).toBeDisabled();
});

test('synthetic selection survives stage navigation and remains marked as demo', async ({ page }) => {
  await page.goto('/'); await page.getByRole('button', { name: /생산계획 비교/ }).click();
  await page.getByRole('button', { name: '안정형 선택' }).click();
  await page.getByRole('button', { name: 'RCCP 능력 검토', exact: true }).click();
  await expect(page.getByRole('img', { name: /포장 설비/ })).toBeVisible();
  await page.screenshot({ path: '../.artifacts/handoff-rccp.png', fullPage: true });
  await page.getByRole('button', { name: 'MRP 자재 검토', exact: true }).click();
  await expect(page.locator('.shortage-cell')).toHaveCount(3);
  await page.getByRole('button', { name: 'MPS 3안', exact: true }).click();
  await expect(page.getByText('선택한 설명 사례: 안정형. 이 선택은 서버에 저장되지 않습니다.')).toBeVisible();
});
