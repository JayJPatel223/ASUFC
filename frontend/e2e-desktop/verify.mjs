import { expect } from '@playwright/test';
import { _electron } from 'playwright';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktop = fileURLToPath(new URL('../../desktop/', import.meta.url));
const requireDesktop = createRequire(path.join(desktop, 'package.json'));
const executablePath = requireDesktop('electron');
const state = await mkdtemp(path.join(tmpdir(), 'asufc-window-'));
const password = 'fictional-app-window-test-only';

async function launch() {
  return _electron.launch({
    executablePath,
    args: [desktop],
    env: { ...process.env, ASUFC_DESKTOP_TEST_DATA: state },
    timeout: 60_000,
  });
}

async function staffLogin(page) {
  await page.getByLabel('Username').fill('staff');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Purchasing credits' })).toBeVisible();
  assert.match(page.url(), /^http:\/\/127\.0\.0\.1:\d+\/$/);
}

try {
  let app = await launch();
  try {
    const page = await app.firstWindow();
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
  } finally {
    await app.close();
  }

  app = await launch();
  try {
    const page = await app.firstWindow();
    await staffLogin(page);
    await expect(page.getByRole('region', { name: 'Cash', exact: true })).toContainText('100.00');
    await expect(page.getByText('Fictional window grant', { exact: true })).toBeVisible();
  } finally {
    await app.close();
  }
} finally {
  await rm(state, { recursive: true, force: true });
}
console.log('Verified the desktop window, first-run setup, sign-in, and saved records after reopening.');
