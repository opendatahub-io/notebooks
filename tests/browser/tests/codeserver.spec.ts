import * as path from "node:path";

import { test as base, expect, chromium } from '@playwright/test';

import {GenericContainer} from "testcontainers";
import {HttpWaitStrategy} from "testcontainers/build/wait-strategies/http-wait-strategy.js";

import {CodeServer} from "./models/codeserver"
import {log} from "./logger"

import {setupTestcontainers} from "./testcontainers";

import * as utils from './utils'
import { assertUnreachable, type ConfigFixtures } from "./fixtures";

// Extend shared config fixture types with test-specific fixtures.
type TestFixtures = ConfigFixtures & {
  codeServer: CodeServer
};
const test = base.extend<TestFixtures>({
  connectCDP: [false, {option: true}],
  codeServerSource: [{kind: 'url', url:'http://localhost:8787'}, {option: true}],
  page: async ({ page, connectCDP }, use) => {
    if (!connectCDP) {
      await use(page)
    } else {
      // we close the provided page and send onwards our own
      await page.close()
      const browser = await chromium.connectOverCDP(`http://localhost:${connectCDP}`);
      try {
        const defaultContext = browser.contexts()[0]!;
        const page = defaultContext.pages()[0]!;
        await use(page)
      } finally {
        // For CDP-connected browsers, close() disconnects without killing the process
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
            .withExposedPorts(8787)
            .withWaitStrategy(new HttpWaitStrategy('/?folder=/opt/app-root/src', 8787, {abortOnContainerExit: true}))
            .start();
        try {
          await use(new CodeServer(page, `http://${container.getHost()}:${container.getMappedPort(8787)}`))
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

test.describe('code-server', { tag: '@codeserver' }, () => {
  test.beforeAll(setupTestcontainers)

  test('open codeserver', async ({codeServer, page}) => {
    await page.goto(codeServer.url)

    expect(await codeServer.isEditorVisible()).toBe(true)
  })

  test('wait for startup surface to load', async ({codeServer, page}, testInfo) => {
    await page.goto(codeServer.url);

    expect(await codeServer.isEditorVisible()).toBe(true)
    page.on("console", (msg) => log.info(msg.text()))

    await utils.assertStartupSurface(page, testInfo)
  })

  test('use the terminal to run command', async ({codeServer, page}, _testInfo) => {
    test.setTimeout(120_000)
    await page.goto(codeServer.url);

    await test.step("Should always see the code-server editor", async () => {
      expect(await codeServer.isEditorVisible()).toBe(true)
    })

    await test.step("should show the Integrated Terminal", async () => {
      await codeServer.focusTerminal()
      await codeServer.waitForTerminalReady()
      await expect(page.locator("#terminal")).toBeVisible()
    })

    await test.step("should execute Terminal command successfully", async () => {
      await codeServer.runTerminalCommand("echo The answer is $(( 6 * 7 )). > answer.txt")
      // Allow the shell redirect to flush before opening the file in the editor.
      await page.waitForTimeout(1000)
    })

    await test.step("should open the file", async() => {
      const file = path.join('/opt/app-root/src', 'answer.txt')
      await codeServer.openFile(file)
      await expect(page.locator(".editor-container").getByText("The answer is 42.", {exact: true})).toBeVisible()
    })

  })
});
