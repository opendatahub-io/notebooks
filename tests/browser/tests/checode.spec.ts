import * as process from "node:process";

import { test as base, expect, chromium } from '@playwright/test';

import {GenericContainer} from "testcontainers";
import {HttpWaitStrategy} from "testcontainers/build/wait-strategies/http-wait-strategy.js";

import {CodeServer} from "./models/codeserver"

import {setupTestcontainers} from "./testcontainers";

import * as utils from './utils'

// CHECODE_URL points at an already-running che-code instance (e.g. via SSH tunnel).
// TEST_TARGET starts a container from a given image.
// Without either, falls back to http://localhost:8888.
const cheCodeUrl = process.env['CHECODE_URL'] ?? '';
const cheCodeImage = process.env['TEST_TARGET'] ?? '';

type TestFixtures = {
  connectCDP: false | number;
  codeServer: CodeServer;
};
const test = base.extend<TestFixtures>({
  connectCDP: [false, {option: true}],
  page: async ({ page, connectCDP }, use) => {
    if (!connectCDP) {
      await use(page)
    } else {
      await page.close()
      const browser = await chromium.connectOverCDP(`http://localhost:${connectCDP}`);
      try {
        const defaultContext = browser.contexts()[0]!;
        const page = defaultContext.pages()[0]!;
        await use(page)
      } finally {
        await browser.close()
      }
    }
  },
  codeServer: [async ({ page }, use) => {
    if (cheCodeUrl) {
      await use(new CodeServer(page, cheCodeUrl));
    } else if (cheCodeImage) {
      const container = await new GenericContainer(cheCodeImage)
          .withExposedPorts(8888)
          .withWaitStrategy(new HttpWaitStrategy('/', 8888, {abortOnContainerExit: true}))
          .start();
      try {
        await use(new CodeServer(page, `http://${container.getHost()}:${container.getMappedPort(8888)}`))
      } finally {
        await container.stop()
      }
    } else {
      await use(new CodeServer(page, 'http://localhost:8888'));
    }
  }, {timeout: 10 * 60 * 1000}],
});

async function loadEditor(codeServer: CodeServer, page: import('@playwright/test').Page) {
  await page.goto(codeServer.url, { timeout: 60000, waitUntil: 'domcontentloaded' });
  expect(await codeServer.isEditorVisible()).toBe(true);
}

async function runCommand(page: import('@playwright/test').Page, command: string) {
  // Ctrl+Shift+P is more reliable than menu navigation for che-code
  await page.keyboard.press('Control+Shift+P');
  await page.waitForSelector('.quick-input-widget', { timeout: 5000 });
  await page.keyboard.type(command, { delay: 50 });
  await page.locator('.quick-input-widget .quick-input-list .monaco-list-row').first().click({ timeout: 5000 });
}

test.describe('che-code', { tag: '@checode' }, () => {
  test.beforeAll(setupTestcontainers)

  test('editor loads', async ({codeServer, page}) => {
    await page.goto(codeServer.url, { timeout: 60000, waitUntil: 'domcontentloaded' })
    expect(await codeServer.isEditorVisible()).toBe(true)
  })

  test('welcome screen renders', async ({codeServer, page}, testInfo) => {
    await loadEditor(codeServer, page)
    await page.waitForTimeout(3000)
    await utils.takeScreenshot(page, testInfo, "welcome.png")
  })

  test('terminal runs a command', { annotation: { type: 'issue', description: 'che-code terminal is broken' } }, async () => {
    test.fixme();
  })

  test('python extension is active', async ({codeServer, page}) => {
    test.setTimeout(60000)
    await loadEditor(codeServer, page)

    await test.step("Python extension is installed", async () => {
      // Use command palette to check — more reliable than Extensions sidebar
      await page.keyboard.press('Control+Shift+P')
      await page.waitForSelector('.quick-input-widget', { timeout: 5000 })
      await page.keyboard.type('Python: ', { delay: 50 })
      // If the Python extension is active, it contributes Python: commands
      await expect(
        page.locator('.quick-input-widget .quick-input-list .monaco-list-row')
            .filter({ hasText: /^Python:/ }).first()
      ).toBeVisible({ timeout: 10000 })
      await page.keyboard.press('Escape')
    })
  })

  test('jupyter notebook can be created', async ({codeServer, page}) => {
    test.setTimeout(90000)
    await loadEditor(codeServer, page)

    await test.step("create new jupyter notebook via command palette", async () => {
      await runCommand(page, 'Create: New Jupyter Notebook')
      // The notebook editor tab shows "Untitled-N.ipynb"
      await expect(page.locator('.tab').filter({ hasText: /\.ipynb/ })).toBeVisible({ timeout: 30000 })
    })

    await test.step("notebook toolbar is visible", async () => {
      // The Jupyter notebook toolbar has Code/Markdown/Run All buttons
      await expect(page.getByRole('button', { name: /Run All/i })).toBeVisible({ timeout: 15000 })
    })
  })

  test('activity tracker writes last-activity file', { annotation: { type: 'issue', description: 'depends on terminal which is broken' } }, async () => {
    test.fixme();
  })
});
