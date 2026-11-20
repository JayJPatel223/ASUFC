import { createHash } from 'node:crypto';
import {test,expect} from '@playwright/test';

test('public build loads and simulates financial workflows without API traffic',async({page, request, baseURL})=>{
 test.setTimeout(120_000);
 const entry = new URL(baseURL!);
 const expectedHash = process.env.ASUFC_PAGES_INDEX_SHA256;
 const hash = (body: Buffer) => createHash('sha256').update(body).digest('hex');
 if (expectedHash) {
  await expect.poll(async () => {
   const probe = new URL(entry);
   probe.searchParams.set('pages-check', String(Date.now()));
   try {
    const response = await request.get(probe.href, {timeout: 5000});
    return response.ok() ? hash(await response.body()) : `HTTP ${response.status()}`;
   } catch (error) {
    return String(error);
   }
  }, {message: 'Public HTML must match the entry point tested before upload', timeout: 75_000, intervals: [1000, 3000, 5000]}).toBe(expectedHash);
  entry.searchParams.set('pages-check', String(Date.now()));
 }

 const unexpected: string[] = [];
 const errors: string[] = [];
 const loadedAssets = new Set<string>();
 await page.route('**/*', async route => {
  const req = route.request();
  const url = new URL(req.url());
  const type = req.resourceType();
  if (url.origin !== entry.origin || !url.pathname.startsWith(entry.pathname) || type === 'fetch' || type === 'xhr') {
   unexpected.push(req.url());
   await route.abort();
   return;
  }
  await route.continue();
 });
 page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
 page.on('pageerror', error => errors.push(error.message));
 page.on('response', response => {
  const type = response.request().resourceType();
  if (response.status() >= 400) errors.push(`HTTP ${response.status()} ${response.url()}`);
  if (response.ok() && new URL(response.url()).pathname.startsWith(`${entry.pathname}assets/`)) loadedAssets.add(type);
 });

 const navigation = await page.goto(entry.href);
 expect(navigation?.ok()).toBe(true);
 if (expectedHash) expect(hash(await navigation!.body())).toBe(expectedHash);
 await page.getByRole('button',{name:'Enter public demo'}).click();
 await expect(page.getByText('Public demonstration — fictional data only.')).toBeVisible();
 for (const [label, amount] of [
  ['Cash received', '13,000.00'], ['Cash spent', '250.00'], ['Cash remaining', '12,750.00'],
  ['Credit remaining', '3,000.00'], ['Expected cash', '2,000.00'], ['Unallocated cash', '6,500.00'],
 ]) {
  await expect(page.locator('.metric').filter({hasText:label})).toContainText(amount);
 }
 await page.getByRole('button',{name:'Transactions',exact:true}).click();
 await page.getByLabel('Purchase date').fill('2026-10-01');
 await page.getByLabel('Supplier',{exact:true}).fill('Demo test shop');
 await page.getByLabel('Purchase type',{exact:true}).fill('Groceries');
 await page.getByLabel('Purchase total (CAD)').fill('100');
 await page.getByLabel('Program / funding').selectOption('1');
 await page.getByLabel('Amount (CAD)',{exact:true}).fill('100');
 await page.getByRole('button',{name:'Confirm and save purchase'}).click();
 await expect(page.getByText('Record saved successfully.')).toBeVisible();
 await page.getByRole('button',{name:'Overview',exact:true}).click();
 await expect(page.locator('.metric').filter({hasText:'Cash remaining'})).toContainText('12,650.00');
 await page.getByRole('button',{name:'Reports',exact:true}).click();
 await expect(page.locator('.metric').filter({hasText:'Cash spent'})).toContainText('350.00');
 await page.getByRole('button',{name:'History',exact:true}).click();
 const option=page.getByLabel('Purchase to void').locator('option').filter({hasText:'Demo test shop'});
 await page.getByLabel('Purchase to void').selectOption(await option.getAttribute('value')||'');
 await page.getByLabel('Reason for voiding').fill('Demo test');page.once('dialog',d=>d.accept());
 await page.getByRole('button',{name:'Confirm void'}).click();
 await expect(page.getByRole('row').filter({hasText:'Demo test shop'})).toContainText('voided');
 await page.reload();await page.getByRole('button',{name:'Enter public demo'}).click();
 await expect(page.locator('.metric').filter({hasText:'Cash remaining'})).toContainText('12,750.00');
 expect(loadedAssets).toEqual(new Set(['script', 'stylesheet']));
 expect(unexpected).toEqual([]);
 expect(errors).toEqual([]);
});
