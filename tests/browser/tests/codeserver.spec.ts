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

    await codeServer.isEditorVisible()
  })

  test('wait for welcome screen to load', async ({codeServer, page}, testInfo) => {
    await page.goto(codeServer.url);

    await codeServer.isEditorVisible()
    page.on("console", (msg) => log.info(msg.text()))

    // With chat.disableAIFeatures:false, Agent Status / Chat keep mutating
    // div.monaco-workbench, so whole-workbench waitForStableDOM never settles.
    // Assert the welcome surface itself instead (title is heading + paragraph).
    await expect(page.getByRole('tab', { name: /Welcome/i })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'code-server', level: 1 })).toBeVisible()
    await expect(page.getByText('Editing evolved')).toBeVisible()
    await utils.waitForNextRender(page)

    await utils.takeScreenshot(page, testInfo, "welcome.png")
  })

  test('use the terminal to run command', async ({codeServer, page}, _testInfo) => {
    await page.goto(codeServer.url);

    await test.step("Should always see the code-server editor", async () => {
      expect(await codeServer.isEditorVisible()).toBe(true)
    })

    await test.step("should show the Integrated Terminal", async () => {
      await codeServer.focusTerminal()
      await expect(page.locator("#terminal")).toBeVisible()
    })

    await test.step("should execute Terminal command successfully", async () => {
      await page.keyboard.type('echo The answer is $(( 6 * 7 )). > answer.txt', {delay: 100})
      await page.keyboard.press('Enter', {delay: 100})
    })

    await test.step("should open the file", async() => {
      const file = path.join('/opt/app-root/src', 'answer.txt')
      await codeServer.openFile(file)
      await expect(page.getByText("The answer is 42.")).toBeVisible()
    })

  })
});
