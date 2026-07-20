import * as path from "node:path";
import * as process from "node:process";

import { test as base, expect, chromium } from '@playwright/test';

import {GenericContainer} from "testcontainers";
import {HttpWaitStrategy} from "testcontainers/build/wait-strategies/http-wait-strategy.js";

import {CodeServer} from "./models/codeserver"
import {log} from "./logger"

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
      await expect(page.locator('.notebook-editor')).toBeVisible({ timeout: 15000 })
    })

    await test.step("kernel selector is available", async () => {
      const kernelButton = page.locator('[aria-label*="kernel" i], [aria-label*="Kernel" i], .kernel-action-view-item')
      await expect(kernelButton.first()).toBeVisible({ timeout: 10000 })
    })
  })

  test('activity tracker writes last-activity file', async ({codeServer, page}) => {
    await page.goto(codeServer.url);
    await codeServer.isEditorVisible()
    await utils.waitForStableDOM(page, "div.monaco-workbench", 1000, 10000)

    await test.step("generate activity by typing in terminal", async () => {
      await codeServer.focusTerminal()
      await page.keyboard.type('cat /tmp/last-activity', {delay: 50})
      await page.keyboard.press('Enter', {delay: 100})
    })

    await test.step("last-activity file has recent timestamp", async () => {
      await page.waitForTimeout(2000)
      await page.keyboard.type('cat /tmp/last-activity', {delay: 50})
      await page.keyboard.press('Enter', {delay: 100})
      await expect(page.locator('#terminal')).toContainText(/\d{4}-\d{2}-\d{2}T/, { timeout: 5000 })
    })
  })
});
