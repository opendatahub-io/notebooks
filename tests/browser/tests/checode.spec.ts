import * as path from "node:path";
import * as process from "node:process";

import { test as base, expect, chromium } from '@playwright/test';

import {GenericContainer} from "testcontainers";
import {HttpWaitStrategy} from "testcontainers/build/wait-strategies/http-wait-strategy.js";

import {CodeServer} from "./models/codeserver"
import {log} from "./logger"

import {setupTestcontainers} from "./testcontainers";

import * as utils from './utils'
import { assertUnreachable, CodeServerSource, type ConfigFixtures } from "./fixtures";

// CHECODE_URL overrides to point at an already-running che-code instance (e.g. via SSH tunnel).
// TEST_TARGET overrides to start a container from a given image.
// Without either, falls back to the default URL.
function cheCodeSource(): CodeServerSource {
  if (process.env['CHECODE_URL']) return CodeServerSource.url(process.env['CHECODE_URL']);
  if (process.env['TEST_TARGET']) return CodeServerSource.image(process.env['TEST_TARGET']);
  return CodeServerSource.url('http://localhost:8888');
}

type TestFixtures = ConfigFixtures & {
  codeServer: CodeServer
};
const test = base.extend<TestFixtures>({
  connectCDP: [false, {option: true}],
  codeServerSource: [cheCodeSource(), {option: true}],
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
  codeServer: [async ({ page, codeServerSource }, use) => {
    switch (codeServerSource.kind) {
      case 'url':
        await use(new CodeServer(page, codeServerSource.url));
        break;
      case 'image': {
        const container = await new GenericContainer(codeServerSource.image)
            .withExposedPorts(8888)
            .withWaitStrategy(new HttpWaitStrategy('/', 8888, {abortOnContainerExit: true}))
            .start();
        try {
          await use(new CodeServer(page, `http://${container.getHost()}:${container.getMappedPort(8888)}`))
        } finally {
          await container.stop()
        }
        break;
      }
      default:
        assertUnreachable(codeServerSource);
    }
  }, {timeout: 10 * 60 * 1000}],
});

test.describe('che-code', { tag: '@checode' }, () => {
  test.beforeAll(setupTestcontainers)

  test('editor loads', async ({codeServer, page}) => {
    await page.goto(codeServer.url)
    expect(await codeServer.isEditorVisible()).toBe(true)
  })

  test('welcome screen renders', async ({codeServer, page}, testInfo) => {
    await page.goto(codeServer.url);
    await codeServer.isEditorVisible()
    page.on("console", (msg) => log.info(msg.text()))

    await utils.waitForStableDOM(page, "div.monaco-workbench", 1000, 10000)
    await utils.waitForNextRender(page)

    await utils.takeScreenshot(page, testInfo, "welcome.png")
  })

  test('terminal runs a command', async ({codeServer, page}) => {
    await page.goto(codeServer.url);

    await test.step("editor is visible", async () => {
      expect(await codeServer.isEditorVisible()).toBe(true)
    })

    await test.step("open integrated terminal", async () => {
      await codeServer.focusTerminal()
      await expect(page.locator("#terminal")).toBeVisible()
    })

    await test.step("run echo command", async () => {
      await page.keyboard.type('echo The answer is $(( 6 * 7 )). > answer.txt', {delay: 100})
      await page.keyboard.press('Enter', {delay: 100})
    })

    await test.step("verify file contents", async() => {
      const file = path.join('/opt/app-root/src', 'answer.txt')
      await codeServer.openFile(file)
      await expect(page.getByText("The answer is 42.")).toBeVisible()
    })
  })

  test('python extension is active', async ({codeServer, page}) => {
    await page.goto(codeServer.url);
    await codeServer.isEditorVisible()
    await utils.waitForStableDOM(page, "div.monaco-workbench", 1000, 15000)

    await test.step("status bar shows Python interpreter", async () => {
      // The Python extension adds an interpreter selector to the status bar.
      // It may show "Select Interpreter" or the detected path like "Python 3.12.x".
      const statusBar = page.locator('.statusbar-item')
      await expect(
        statusBar.filter({ hasText: /Python|Select Interpreter/ })
      ).toBeVisible({ timeout: 30000 })
    })
  })

  test('jupyter notebook can be created', async ({codeServer, page}) => {
    await page.goto(codeServer.url);
    await codeServer.isEditorVisible()
    await utils.waitForStableDOM(page, "div.monaco-workbench", 1000, 15000)

    await test.step("create new jupyter notebook via command palette", async () => {
      await codeServer.executeCommandViaMenus("Create: New Jupyter Notebook")
      // Wait for the notebook editor to appear
      await expect(page.locator('.notebook-editor')).toBeVisible({ timeout: 15000 })
    })

    await test.step("kernel selector is available", async () => {
      // The Jupyter extension shows a kernel picker button in the notebook toolbar
      const kernelButton = page.locator('[aria-label*="kernel" i], [aria-label*="Kernel" i], .kernel-action-view-item')
      await expect(kernelButton.first()).toBeVisible({ timeout: 10000 })
    })
  })

  test('activity tracker writes last-activity file', async ({codeServer, page}, testInfo) => {
    await page.goto(codeServer.url);
    await codeServer.isEditorVisible()
    await utils.waitForStableDOM(page, "div.monaco-workbench", 1000, 10000)

    await test.step("generate activity by typing in terminal", async () => {
      await codeServer.focusTerminal()
      await page.keyboard.type('cat /tmp/last-activity', {delay: 50})
      await page.keyboard.press('Enter', {delay: 100})
    })

    // The kubeflow-activity-tracker extension writes ISO timestamps to /tmp/last-activity
    // on any editor activity. After using the terminal, the file should exist.
    await test.step("last-activity file has recent timestamp", async () => {
      // Small delay to let the extension write
      await page.waitForTimeout(2000)
      await page.keyboard.type('cat /tmp/last-activity', {delay: 50})
      await page.keyboard.press('Enter', {delay: 100})
      // The terminal should show an ISO 8601 timestamp
      await expect(page.locator('#terminal')).toContainText(/\d{4}-\d{2}-\d{2}T/, { timeout: 5000 })
    })
  })
});
