import { expect, type Page } from '@playwright/test';

/** Prepared acceptance scenario. Not registered as a runnable test until dataset UI exists.
 * Proposed accessible names/test IDs must be agreed with the frontend owner.
 * Only run against the explicitly authorized regression API, never the development DB.
 */
export async function verifyDatasetSelection(page: Page, apiBase: string): Promise<void> {
  const datasets = await page.request.get(`${apiBase}/datasets`);
  expect(datasets.ok()).toBeTruthy();
  expect((await datasets.json()).map((d: { dataset_id: string }) => d.dataset_id))
    .toEqual(expect.arrayContaining(['TISSUE-LEGACY', 'CHUNGPAMO-2027']));
  await page.goto('/');
  const selector = page.getByRole('combobox', { name: '데이터셋' });
  await expect(selector).toBeVisible();
  const cpProducts = page.waitForResponse(r => r.url().includes('/products') && new URL(r.url()).searchParams.get('dataset_id') === 'CHUNGPAMO-2027');
  await selector.selectOption('CHUNGPAMO-2027');
  expect((await (await cpProducts).json()).total).toBe(9);
  await page.getByRole('button', { name: '수요예측' }).click();
  const run = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/forecasts');
  await page.getByRole('button', { name: '예측 실행' }).click();
  const execution = (await (await run).json()).execution;
  expect(execution.dataset_id).toBe('CHUNGPAMO-2027');
  await expect(page.getByTestId('forecast-results')).toBeVisible();
  for (const endpoint of ['/capacity', '/routings']) {
    const response = await page.request.get(`${apiBase}${endpoint}?dataset_id=CHUNGPAMO-2027`);
    expect(response.ok()).toBeTruthy();
    expect((await response.json()).total).toBe(27);
  }
  const capabilities = await page.request.get(`${apiBase}/integrations/modules`);
  expect((await capabilities.json()).planning).toBe('IMPLEMENTED');
  const legacyProducts = page.waitForResponse(r => r.url().includes('/products') && new URL(r.url()).searchParams.get('dataset_id') === 'TISSUE-LEGACY');
  await selector.selectOption('TISSUE-LEGACY');
  const legacy = await (await legacyProducts).json();
  expect(legacy.total).toBe(1);
  expect(legacy.items[0].product_id).toBe('TP-10R');
  await expect(page.getByTestId('forecast-execution-select')).not.toHaveValue(execution.execution_id);
}
