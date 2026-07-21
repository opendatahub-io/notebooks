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

// Skip test.setTimeout when a debugger is attached — the fixed timeout
// kills interactive debugging sessions.
const DEBUGGER_ATTACHED = typeof (globalThis as any).v8debug === 'object'
    || /--inspect/.test(process.execArgv.join(' '));
function safeTimeout(t: import('@playwright/test').TestType<any, any>, ms: number) {
  if (!DEBUGGER_ATTACHED) t.setTimeout(ms);
}

async function loadEditor(codeServer: CodeServer, page: import('@playwright/test').Page) {
  await page.goto(codeServer.url, { timeout: 60000, waitUntil: 'domcontentloaded' });
  expect(await codeServer.isEditorVisible()).toBe(true);
}

async function runCommand(page: import('@playwright/test').Page, command: string) {
  await page.keyboard.press('Control+Shift+P');
  await page.waitForSelector('.quick-input-widget', { timeout: 5000 });
  await page.keyboard.type(command, { delay: 50 });
  await page.waitForTimeout(1000);
  // Wait for the exact command to appear and click it, or press Enter if it's the first match
  const exactRow = page.locator('.quick-input-widget .monaco-list-row')
      .filter({ hasText: new RegExp(command.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i') });
  if (await exactRow.count() > 0) {
    await exactRow.first().click({ timeout: 5000 }).catch(() => page.keyboard.press('Enter'));
  } else {
    await page.keyboard.press('Enter');
  }
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
    safeTimeout(test, 60000)
    await loadEditor(codeServer, page)

    await test.step("wait for extensions to activate", async () => {
      // Poll until Python commands appear — extension activation is async
      await expect(async () => {
        await page.keyboard.press('Control+Shift+P')
        await page.waitForSelector('.quick-input-widget', { timeout: 3000 })
        await page.keyboard.type('Python: ', { delay: 30 })
        const row = page.locator('.quick-input-widget .quick-input-list .monaco-list-row')
            .filter({ hasText: /Python:/ }).first()
        await expect(row).toBeVisible({ timeout: 3000 })
        await page.keyboard.press('Escape')
      }).toPass({ timeout: 45000, intervals: [2000, 3000, 5000] })
    })
  })

  test('jupyter notebook can be created and executed', async ({codeServer, page}) => {
    safeTimeout(test, 120000)
    await loadEditor(codeServer, page)

    await test.step("create new jupyter notebook via command palette", async () => {
      await runCommand(page, 'Create: New Jupyter Notebook')
      await expect(page.locator('.tab').filter({ hasText: /\.ipynb/ })).toBeVisible({ timeout: 30000 })
    })

    await test.step("notebook toolbar is visible", async () => {
      await expect(page.getByRole('button', { name: /Run All/i })).toBeVisible({ timeout: 15000 })
    })

    await test.step("select app-root Python kernel", async () => {
      const selectKernel = page.getByRole('button', { name: /Select Kernel/i })
      await expect(selectKernel.first()).toBeVisible({ timeout: 10000 })
      await selectKernel.first().click()

      // Pick "Python Environments..."
      await page.waitForSelector('.quick-input-widget', { timeout: 5000 })
      await page.keyboard.type('Python Env', { delay: 30 })
      await page.waitForTimeout(1000)
      await page.keyboard.press('Enter')
      await page.waitForTimeout(2000)

      // Filter for app-root (has ipykernel pre-installed, works air-gapped)
      await page.keyboard.type('app-root', { delay: 30 })
      await page.waitForTimeout(1000)
      await page.keyboard.press('Enter')

      // Verify kernel is connected
      await expect(page.getByRole('button', { name: /Restart/i })).toBeVisible({ timeout: 30000 })
    })

    await test.step("dismiss any dialogs", async () => {
      await page.keyboard.press('Escape')
      await page.waitForTimeout(1000)
    })

    await test.step("type expression into cell", async () => {
      // Click the cell editor area to focus it
      const cellEditor = page.locator('.cell-editor-container .monaco-editor')
      await expect(cellEditor.first()).toBeVisible({ timeout: 10000 })
      await cellEditor.first().click()
      await page.waitForTimeout(500)
      await page.keyboard.type('3 + 4')
    })

    await test.step("execute cell and verify completion", async () => {
      await page.keyboard.press('Control+Enter')
      // Execution time (e.g. "0.0s") appears in the ARIA tree on completion
      await expect(async () => {
        const snap = await page.ariaSnapshot()
        expect(snap).toMatch(/\d+\.\d+s\s+Python/)
      }).toPass({ timeout: 30000 })
    })

    await test.step("no runtime package installation occurred", async () => {
      // If ipykernel is missing, VS Code installs it at runtime — a regression
      // for air-gapped deployments. Check that no "Installing" notification appeared.
      const snap = await page.ariaSnapshot()
      expect(snap).not.toContain('Installing ipykernel')
      expect(snap).not.toContain('Installing collected package')
    })
  })

  test('activity tracker writes last-activity file', { annotation: { type: 'issue', description: 'depends on terminal which is broken' } }, async () => {
    test.fixme();
  })
});
