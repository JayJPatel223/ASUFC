// Test-only entry point. This file is excluded from the desktop package.
const { app } = require('electron');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { setTimeout: wait } = require('node:timers/promises');

const windowCreated = once(app, 'browser-window-created');
require('../../desktop/main.cjs');
const password = 'fictional-app-window-test-only';
const setup = process.env.ASUFC_DESKTOP_TEST_PHASE === 'setup';

async function check(window) {
  const evaluate = expression => window.webContents.executeJavaScript(expression, true);
  async function waitFor(expression, label) {
    const deadline = Date.now() + 40_000;
    while (Date.now() < deadline) {
      try {
        if (await evaluate(expression)) return;
      } catch {
        // React and the setup screen replace the window's document during navigation.
      }
      await wait(200);
    }
    throw new Error('The desktop window did not show ' + label);
  }

  const fillForm = async (form, fields) => {
    const filled = await evaluate(`(() => {
      const form = ${form};
      if (!form) return false;
      for (const [name, value] of Object.entries(${JSON.stringify(fields)})) form.elements.namedItem(name).value = value;
      form.requestSubmit();
      return true;
    })()`);
    assert.ok(filled);
  };
  const button = label => `Array.from(document.querySelectorAll('button')).find(node => node.textContent.trim() === ${JSON.stringify(label)})`;

  if (setup) {
    await waitFor('location.protocol === "file:" && !!document.querySelector("input[name=confirmation]")', 'first-run setup');
    await fillForm('document.querySelector("form")', { password: password, confirmation: password });
  }
  await waitFor('location.hostname === "127.0.0.1" && !!document.querySelector("input[name=user]")', 'the staff sign-in form');
  await fillForm('document.querySelector("form")', { user: 'staff', password: password });
  await waitFor('document.querySelector("h1")?.textContent === "Overview"', 'the staff overview');

  if (setup) {
    await evaluate(button('Funding & grants') + '.click()');
    const panel = 'Array.from(document.querySelectorAll("section")).find(node => node.querySelector("h2")?.textContent === "Add funding")';
    await waitFor('!!(' + panel + ')', 'the funding form');
    await fillForm(panel + '.querySelector("form")', {
      name: 'Fictional window grant', award: '120', received: '100',
    });
    await waitFor('document.body.innerText.includes("Record saved successfully.")', 'the funding confirmation');
    await evaluate(button('Sign out') + '.click()');
    await waitFor('!!document.querySelector("input[name=user]")', 'the sign-in page after logout');
  } else {
    await waitFor('document.getElementById("cash-overview")?.parentElement.innerText.includes("100.00")', 'the saved cash balance');
    await waitFor('Array.from(document.querySelectorAll("tr")).some(row => row.innerText.includes("Fictional window grant"))', 'the saved funding record');
  }
}

windowCreated.then(([, window]) => check(window)).then(() => {
  console.log(setup ? 'Verified setup, sign-in and a funding write in the Windows window.' : 'Verified the saved funding record after reopening the Windows window.');
  app.quit();
}).catch(error => {
  console.error(error);
  app.once('will-quit', () => app.exit(1));
  app.quit();
});
