import { test, expect } from '@playwright/test';

test('real API errors never turn into fixture approvals or forecasts', async ({ page, request }) => {
  const modules = await request.get('http://127.0.0.1:8001/integrations/modules');
  expect(modules.status()).toBe(200);
  expect((await modules.json()).planning).toBe('IMPLEMENTED');
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('PERSISTENCE_DISABLED');
  await expect(page.getByLabel('등록 파일 (CSV/XLSX)', { exact: true })).toBeDisabled();
  await page.getByRole('navigation', { name: '업무 메뉴' }).getByRole('button', { name: '수요예측', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('PERSISTENCE_DISABLED');
  await expect(page.getByRole('region', { name: '저장된 예측 결과' })).toHaveCount(0);
  await expect(page.getByRole('img')).toHaveCount(0);
});

test('PPT workflow is interactive but does not fake planning or approval', async ({ page, request }) => {
  const response = await request.post('http://127.0.0.1:8001/plans', { data: {
    forecast_execution_id: '00000000-0000-4000-8000-000000000001', product_ids: ['TP-10R'],
    target_month: '2027-01', as_of_date: '2026-12-31',
  } });
  expect(response.status()).toBe(501);
  expect((await response.json()).detail.code).toBe('PERSISTENCE_DISABLED');
  await page.goto('/');
  await page.getByRole('button', { name: /생산계획 비교/ }).click();
  await expect(page.getByText(/DEMO \/ UNVERIFIED —/)).toBeVisible();
  await page.getByRole('button', { name: '안정형 선택', exact: true }).click();
  await expect(page.getByRole('button', { name: '선택됨', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'RCCP 능력 검토', exact: true }).click();
  await expect(page.getByRole('table')).toContainText('미검증');
  await page.getByRole('button', { name: 'MRP 자재 검토', exact: true }).click();
  await expect(page.getByText('휴지 롤 · 10롤/팩')).toBeVisible();
  await page.getByRole('button', { name: 'What-if', exact: true }).click();
  await page.getByLabel('월 생산량 후보', { exact: true }).fill('8500');
  await expect(page.locator('output')).toHaveText('8,500팩');
  await expect(page.getByRole('button', { name: /재검증 —/ })).toBeDisabled();
  await page.getByRole('button', { name: '최종 MPS', exact: true }).click();
  await expect(page.getByRole('button', { name: '최종 MPS 승인 (미구현)' })).toBeDisabled();
  await page.getByRole('button', { name: '기존 DEMO Excel 출력 안내' }).click();
  await expect(page.getByRole('dialog')).toContainText('승인·검증 증거가 아닙니다');
  await page.getByRole('button', { name: '닫기', exact: true }).click();
  await page.screenshot({ path: '../.artifacts/planning-shell.png', fullPage: true });
});

test('mobile navigation preserves visible manual upload and module boundaries', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: '업무 메뉴' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: '업무 메뉴' }).getByRole('button', { name: '데이터 업로드', exact: true })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});
