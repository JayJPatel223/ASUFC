import { expect } from '@playwright/test';
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createRequire } from 'node:module';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
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
  const listener = createServer().listen(0, '127.0.0.1');
  await once(listener, 'listening');
  const { port } = listener.address();
  await new Promise(resolve => listener.close(resolve));
  const endpoint = 'http://127.0.0.1:' + port;
  const child = spawn(executablePath, [`--remote-debugging-port=${port}`, desktop], {
    env: { ...process.env, ASUFC_DESKTOP_TEST_DATA: state },
    stdio: ['ignore', 'ignore', 'inherit'],
    windowsHide: true,
  });
  const exited = once(child, 'exit');
  let browser;
  try {
    for (let attempt = 0; attempt < 120; attempt++) {
      if (child.exitCode !== null || child.signalCode !== null) throw new Error('The desktop application exited before opening.');
      try {
        const response = await fetch(endpoint + '/json/version', {signal: AbortSignal.timeout(500)});
        if (response.ok) break;
      } catch {
        // The window can start before Electron's test debugging endpoint.
      }
      if (attempt === 119) throw new Error('Electron did not expose the local test endpoint.');
      await wait(500);
    }
    browser = await chromium.connectOverCDP(endpoint);
    const context = browser.contexts()[0];
    const page = context.pages()[0] ?? await context.waitForEvent('page', {timeout: 60_000});
    return {
      page,
      async close() {
        await page.close();
        const result = await Promise.race([exited, wait(45_000, null, {ref: false})]);
        if (!result) {
          child.kill();
          throw new Error('The desktop application did not close the ledger.');
        }
        assert.equal(result[0], 0);
        await browser.close();
      },
    };
  } catch (error) {
    await browser?.close();
    child.kill();
    throw error;
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

try {
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
} catch (error) {
  const log = await readFile(path.join(state, 'staff-data', 'desktop.log'), 'utf8').catch(() => '');
  if (log) console.error(log);
  throw error;
} finally {
  await rm(state, { recursive: true, force: true });
}
console.log('Verified the desktop window, first-run setup, sign-in, and saved records after reopening.');
