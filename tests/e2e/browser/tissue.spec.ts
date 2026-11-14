import { test, expect } from '@playwright/test';
import path from 'node:path';

test('single tissue product approval to stored forecast chart and reload', async ({ page }) => {
  const ready = () => expect(page.getByRole('status')).toHaveText('서버 상태 조회 완료');
  await page.goto('/'); await ready();
  for (const [label, file] of [['제품', 'products'], ['자재', 'materials'], ['BOM', 'bom'], ['재고', 'inventory'], ['월별 수요', 'demand']]) {
    await page.getByRole('complementary', { name: '데이터 종류' }).getByRole('button', { name: new RegExp(`^${label}`) }).click();
    await page.getByLabel('데이터 출처', { exact: true }).selectOption('SYNTHETIC');
    await page.getByLabel('출처 설명', { exact: true }).fill('single-product tissue synthetic E2E');
    const uploaded = page.waitForResponse(r => r.url().endsWith('/batches') && r.request().method() === 'POST');
    await page.getByLabel('등록 파일 (CSV/XLSX)', { exact: true }).setInputFiles(path.resolve(`../contracts/examples/tissue_${file}.csv`));
    expect((await uploaded).status()).toBe(201);
    await ready();
    await expect(page.getByRole('button', { name: '검증 결과 승인', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: '검증 결과 승인', exact: true }).click(); await ready();
    await expect(page.getByRole('region', { name: `${label} 배치` })).toContainText('승인 완료');
  }
  await page.getByRole('button', { name: '승인 수요 예측', exact: true }).click();
  await expect(page.getByRole('button', { name: '예측 실행', exact: true })).toBeEnabled();
  await page.getByLabel('학습 기준일 (월말)', { exact: true }).fill('2026-12-31');
  await page.getByLabel('예측 기간 (개월)', { exact: true }).selectOption('1');
  // Provide every parameter explicitly: another saved run may restore different conditions.
  await page.getByLabel('P50 방식', { exact: true }).selectOption('MA12');
  await page.getByLabel('최소 이력 (개월)', { exact: true }).fill('12');
  await page.getByLabel('재현 시드', { exact: true }).fill('42');
  const pending = page.waitForResponse(r => r.url().endsWith('/forecasts') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '예측 실행', exact: true }).click();
  const response = await pending; expect(response.status()).toBe(201);
  const stored = (await response.json()).execution;
  expect(stored.input_row_count).toBe(24);
  expect(stored.forecast_count).toBe(1);
  expect(stored.result.forecasts).toHaveLength(1);
  expect(stored.result.forecasts.some((row: { product_id: string; target_month: string }) => row.product_id === 'TP-10R' && row.target_month === '2027-01')).toBe(true);
  await page.getByLabel('차트 제품', { exact: true }).selectOption('TP-10R');
  await expect(page.getByRole('img', { name: 'TP-10R 월별 P50 P80 P90 예측', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'P90', exact: true }).click();
  await expect(page.getByRole('button', { name: 'P90', exact: true })).toHaveAttribute('aria-pressed', 'false');
  await page.reload();
  await expect(page.getByLabel('저장된 실행', { exact: true })).toHaveValue(stored.execution_id);
  await page.getByLabel('차트 제품', { exact: true }).selectOption('TP-10R');
  await expect(page.getByRole('img', { name: 'TP-10R 월별 P50 P80 P90 예측', exact: true })).toBeVisible();
  await page.screenshot({ path: '../.artifacts/tissue-forecast.png', fullPage: true });
});
