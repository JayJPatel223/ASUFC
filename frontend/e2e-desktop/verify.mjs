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

const desktop = path.resolve(fileURLToPath(new URL('../../desktop/', import.meta.url)));
const requireDesktop = createRequire(path.join(desktop, 'package.json'));
const executablePath = requireDesktop('electron');
const state = await mkdtemp(path.join(tmpdir(), 'asufc-window-'));
const password = 'fictional-app-window-test-only';

async function launch() {
  const app = await _electron.launch({
    executablePath, args: [desktop], env: { ...process.env, ASUFC_DESKTOP_TEST_DATA: state },
    timeout: 60_000,
  });
  return { page: await app.firstWindow(), close: () => app.close() };
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

async function staffLogin(page) {
  await page.getByLabel('Username').fill('staff');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Purchasing credits' })).toBeVisible();
  assert.match(page.url(), /^http:\/\/127\.0\.0\.1:\d+\/$/);
}

async function verifyPlaywrightWindow() {
  let app = await launch();
  try {
    const { page } = app;
    await expect(page.getByRole('heading', { name: 'Set up ASUFC Finance' })).toBeVisible({ timeout: 60_000 });
    await page.getByLabel('New password').fill(password);
    await page.getByLabel('Confirm password').fill(password);
    await page.getByRole('button', { name: 'Create staff login' }).click();
    await staffLogin(page);
    await page.getByRole('button', { name: 'Funding & grants', exact: true }).click();
    const panel = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Add funding', exact: true }) });
    await panel.getByLabel('Funding source', { exact: true }).fill('Fictional window grant');
    await panel.getByLabel('Total award (CAD)').fill('120');
    await panel.getByLabel('Confirmed received (CAD)').fill('100');
    await panel.getByRole('button', { name: 'Save funding' }).click();
    await expect(page.getByText('Record saved successfully.')).toBeVisible();
    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  } finally {
    await app.close();
  }

  app = await launch();
  try {
    const { page } = app;
    await staffLogin(page);
    await expect(page.getByRole('region', { name: 'Cash', exact: true })).toContainText('100.00');
    await expect(page.getByRole('row', { name: /Fictional window grant/ })).toBeVisible();
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
console.log('Verified the desktop window, first-run setup, sign-in, and saved records after reopening.');
