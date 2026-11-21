import { expect } from '@playwright/test';
import { _electron } from 'playwright';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createRequire } from 'node:module';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { setTimeout as wait } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import insertFictionalReceipt from './fictional-receipt.cjs';

const desktop = path.resolve(fileURLToPath(new URL('../../desktop/', import.meta.url)));
const requireDesktop = createRequire(path.join(desktop, 'package.json'));
const executablePath = requireDesktop('electron');
const state = await mkdtemp(path.join(tmpdir(), 'asufc-window-'));

async function launch(profile = state) {
  const app = await _electron.launch({
    executablePath, args: [desktop], env: { ...process.env, ASUFC_DESKTOP_TEST_DATA: profile },
    timeout: 60_000,
  });
  return { app, page: await app.firstWindow(), close: () => app.close() };
}

async function verifyWindowsWindow() {
  const entry = fileURLToPath(new URL('./windows-check.cjs', import.meta.url));
  for (const phase of ['setup', 'reopen']) {
    const child = spawn(executablePath, [entry], {
      env: { ...process.env, ASUFC_DESKTOP_TEST_DATA: state, ASUFC_DESKTOP_TEST_PHASE: phase },
      stdio: 'inherit',
    });
    const result = await Promise.race([once(child, 'exit'), wait(90_000, null, {ref: false})]);
    if (!result) {
      child.kill();
      throw new Error('The Windows window check timed out during ' + phase);
    }
    assert.equal(result[0], 0, 'The Windows window check failed during ' + phase);
  }
}

async function verifyDirectLaunch(page) {
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('heading', { name: 'Purchasing credits' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toHaveCount(0);
  assert.match(page.url(), /^http:\/\/127\.0\.0\.1:\d+\/$/);
  assert.equal((await fetch(new URL('/api/funding', page.url()))).status, 401);
}

async function verifyPlaywrightWindow() {
  const backup = path.join(state, 'fictional-window.asufcbak');
  const passphrase = 'fictional-window-backup-only';
  let app = await launch();
  try {
    const { page } = app;
    await verifyDirectLaunch(page);
    await page.getByRole('button', { name: 'Funding & grants', exact: true }).click();
    const panel = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Add funding', exact: true }) });
    await panel.getByLabel('Funding source', { exact: true }).fill('Fictional window grant');
    await panel.getByLabel('Total award (CAD)').fill('120');
    await panel.getByLabel('Confirmed received (CAD)').fill('100');
    await panel.getByRole('button', { name: 'Save funding' }).click();
    await expect(page.getByText('Record saved successfully.')).toBeVisible();
    await page.getByRole('button', { name: 'Transactions', exact: true }).click();
    await page.getByText('Read a receipt photo', {exact: true}).click();
    await expect(page.getByLabel('Receipt photo')).toBeVisible();
    await page.evaluate(insertFictionalReceipt);
    await page.getByRole('button', {name: 'Read receipt photo'}).click();
    await expect(page.getByLabel('Suggested receipt total')).toHaveValue('12.50', {timeout: 40_000});
    await expect(page.getByLabel('Suggested receipt date')).toHaveValue('2026-11-04');
    await expect(page.getByLabel('Purchase total (CAD)')).toHaveValue('');
    await page.getByRole('button', {name: 'Copy reviewed values to purchase'}).click();
    await expect(page.getByLabel('Purchase total (CAD)')).toHaveValue('12.50');
    await page.getByRole('button', { name: 'Account', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Save encrypted backup' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Restore an encrypted backup' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Change password' })).toHaveCount(0);
    await app.app.evaluate(({BrowserWindow}, file) => {
      BrowserWindow.getAllWindows()[0].webContents.session.once('will-download', (_event, item) => item.setSavePath(file));
    }, backup);
    await page.getByLabel('Backup passphrase', {exact: true}).fill(passphrase);
    await page.getByLabel('Confirm backup passphrase', {exact: true}).fill(passphrase);
    await page.getByRole('button', {name: 'Save encrypted backup'}).click();
    await expect.poll(async () => (await readFile(backup).catch(() => Buffer.alloc(0))).length).toBeGreaterThan(32);
  } finally {
    await app.close();
  }

  app = await launch();
  try {
    const { page } = app;
    await verifyDirectLaunch(page);
    await expect(page.getByRole('region', { name: 'Cash', exact: true })).toContainText('100.00');
    await expect(page.getByRole('row', { name: /Fictional window grant/ })).toBeVisible();
  } finally {
    await app.close();
  }

  app = await launch(path.join(state, 'recovered'));
  try {
    const {page} = app;
    await verifyDirectLaunch(page);
    await app.app.evaluate(({dialog}, file) => {
      dialog.showOpenDialog = async () => ({canceled: false, filePaths: [file]});
    }, backup);
    await page.getByRole('button', {name: 'Account', exact: true}).click();
    await page.getByRole('button', {name: 'Choose backup file'}).click();
    await expect(page.getByText(path.basename(backup), {exact: true})).toBeVisible();
    await page.getByLabel('Passphrase from the selected backup').fill(passphrase);
    await page.getByRole('button', {name: 'Restore backup', exact: true}).click();
    await verifyDirectLaunch(page);
    await expect(page.getByRole('row', {name: /Fictional window grant/})).toBeVisible();
  } finally {
    await app.close();
  }
}

try {
  if (process.platform === 'win32') await verifyWindowsWindow();
  else await verifyPlaywrightWindow();
} catch (error) {
  const log = await readFile(path.join(state, 'staff-data', 'desktop.log'), 'utf8').catch(() => '');
  if (log) console.error(log);
  throw error;
} finally {
  await rm(state, { recursive: true, force: true, maxRetries: 12, retryDelay: 250 });
}
console.log('Verified direct desktop launch, restricted local access, receipt-photo reading and saved records after reopening.');
