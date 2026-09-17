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
const DEBUGGER_ATTACHED = typeof (globalThis as { v8debug?: object }).v8debug === 'object'
    || /--inspect/.test(process.execArgv.join(' '));
function safeTimeout(ms: number) {
  if (!DEBUGGER_ATTACHED) test.setTimeout(ms);
}

async function loadEditor(codeServer: CodeServer, page: import('@playwright/test').Page) {
  await page.goto(codeServer.url, { timeout: 60000, waitUntil: 'domcontentloaded' });
  expect(await codeServer.isEditorVisible()).toBe(true);
}

/** Type a command into the VS Code command palette and select the first match. */
async function runCommand(page: import('@playwright/test').Page, command: string) {
  await page.keyboard.press('Control+Shift+P');
  await page.waitForSelector('.quick-input-widget', { timeout: 5000 });
  await page.keyboard.type(command, { delay: 50 });
  // Wait for the matching row to appear as the first result before pressing Enter
  const pattern = new RegExp(command.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
  await expect(async () => {
    const firstLabel = await page.locator('.quick-input-widget .monaco-list-row').first()
        .getAttribute('aria-label')
    expect(firstLabel).toMatch(pattern)
  }).toPass({ timeout: 10000 })
  await page.keyboard.press('Enter');
}

/** Wait for a quick-input option matching `text` to appear, then press Enter. */
async function pickQuickInputOption(page: import('@playwright/test').Page, text: string) {
  await page.keyboard.type(text, { delay: 30 });
  const option = page.locator('.quick-input-widget .monaco-list-row').filter({ hasText: new RegExp(text, 'i') });
  await expect(option.first()).toBeVisible({ timeout: 10000 });
  await page.keyboard.press('Enter');
}

async function focusCheCodeTerminal(page: import('@playwright/test').Page) {
  await runCommand(page, 'Terminal: Create New Terminal')
  await expect(page.locator('#terminal')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('textarea.xterm-helper-textarea')).toBeVisible({ timeout: 15000 })
  await page.locator('textarea.xterm-helper-textarea').focus()
}

test.describe('che-code', { tag: '@checode' }, () => {
  test.beforeAll(setupTestcontainers)

  test('editor loads', async ({codeServer, page}) => {
    await page.goto(codeServer.url, { timeout: 60000, waitUntil: 'domcontentloaded' })
    expect(await codeServer.isEditorVisible()).toBe(true)
  })

  test('welcome screen renders', async ({codeServer, page}, testInfo) => {
    await loadEditor(codeServer, page)
    await utils.waitForStableDOM(page, ".part.editor", 1000, 15000)
    await utils.takeScreenshot(page, testInfo, "welcome.png")
  })

  test('terminal runs a command', async ({codeServer, page}) => {
    safeTimeout(90000)
    await loadEditor(codeServer, page)

    await test.step("open the integrated terminal", async () => {
      await focusCheCodeTerminal(page)
    })

    await test.step("execute a terminal command", async () => {
      await page.keyboard.type("printf 'Che Code terminal works\\n'")
      await page.keyboard.press('Enter')
      await expect(page.locator('.xterm-rows')).toContainText('Che Code terminal works', { timeout: 15000 })
    })
  })

  test('python extension is active', async ({codeServer, page}) => {
    safeTimeout(60000)
    await loadEditor(codeServer, page)

    await test.step("wait for extensions to activate", async () => {
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
    safeTimeout(120000)
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
      await page.waitForSelector('.quick-input-widget', { timeout: 5000 })

      // Use the explicit kernelspec rather than Python Environment Tools. The
      // latter depends on pet, which is unavailable in the ARM64 image.
      await pickQuickInputOption(page, 'Jupyter Kernel')

      // Filter for the registered workbench kernelspec (works air-gapped).
      await pickQuickInputOption(page, 'app-root')

      // Wait for kernel picker to close and kernel name to appear in toolbar
      await expect(async () => {
        // Dismiss any lingering quick-input or dialog
        if (await page.locator('.quick-input-widget').isVisible().catch(() => false)) {
          await page.keyboard.press('Escape')
        }
        const snap = await page.ariaSnapshot()
        expect(snap).toContain('app-root')
        expect(snap).not.toMatch(/Select Kernel.*Jupyter Kernels/s)
      }).toPass({ timeout: 30000 })
    })

    await test.step("type expression into cell", async () => {
      const cellEditor = page.locator('.cell-editor-container .monaco-editor')
      await expect(cellEditor.first()).toBeVisible({ timeout: 10000 })
      await cellEditor.first().click()
      await page.keyboard.type('3 + 4')
      // Verify the expression appeared in the cell
      await expect(page.locator('.cell-editor-container .view-line').first()).toContainText('3 + 4', { timeout: 5000 })
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
      const snap = await page.ariaSnapshot()
      expect(snap).not.toContain('Installing ipykernel')
      expect(snap).not.toContain('Installing collected package')
    })
  })

  test('activity tracker writes last-activity file', async ({codeServer, page}) => {
    safeTimeout(90000)
    await loadEditor(codeServer, page)

    const getLastActivity = async (): Promise<number> => {
      const response = await page.request.get(`${codeServer.url}/api/kernels/`)
      expect(response.ok()).toBe(true)
      const kernels = await response.json() as Array<{ last_activity: string }>
      expect(kernels).toHaveLength(1)
      return Date.parse(kernels[0]!.last_activity)
    }

    const before = await getLastActivity()

    // The activity tracker debounces writes for five seconds. Wait until the
    // initial timestamp is outside that window before generating terminal input.
    await expect.poll(() => Date.now() - before, { timeout: 15000 }).toBeGreaterThan(5000)

    await focusCheCodeTerminal(page)
    await page.keyboard.type("echo activity")
    await page.keyboard.press('Enter')

    await expect.poll(getLastActivity, { timeout: 30000, intervals: [1000, 2000, 5000] })
      .toBeGreaterThan(before)
  })
});
