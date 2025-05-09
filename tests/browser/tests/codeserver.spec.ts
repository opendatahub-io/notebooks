import * as path from "node:path";

import { test as base, expect, chromium } from '@playwright/test';

import {GenericContainer} from "testcontainers";
import {HttpWaitStrategy} from "testcontainers/build/wait-strategies/http-wait-strategy.js";

import {CodeServer} from "./models/codeserver"

import {setupTestcontainers} from "./testcontainers";

import * as utils from './utils'

// Declare the types of your fixtures.
type MyFixtures = {
  connectCDP: false | number;
  codeServerSource: {url?: string, image?: string};
  codeServer: CodeServer
};
const test = base.extend<MyFixtures>({
  connectCDP: [false, {option: true}],
  codeServerSource: [{url:'http://localhost:8787'}, {option: true}],
  page: async ({ page, connectCDP }, use) => {
    if (!connectCDP) {
      await use(page)
    } else {
      // we close the provided page and send onwards our own
      await page.close()
      {
        const browser = await chromium.connectOverCDP(`http://localhost:${connectCDP}`);
        const defaultContext = browser.contexts()[0];
        const page = defaultContext.pages()[0];
        await use(page)
      }
    }
  },
  codeServer: [async ({ page, codeServerSource }, use) => {
    if (codeServerSource?.url) {
      await use(new CodeServer(page, codeServerSource.url))
    } else {
      const image = codeServerSource.image ?? (() => {
        throw new Error("invalid config: codeserver image not specified")
      })()
      const container = await new GenericContainer(image)
          .withExposedPorts(8787)
          .withWaitStrategy(new HttpWaitStrategy('/', 8787, {abortOnContainerExit: true}))
          .start();
      await use(new CodeServer(page, `http://${container.getHost()}:${container.getMappedPort(8787)}`))
      await container.stop()
    }
  }, {timeout: 10 * 60 * 1000}],
});

test.beforeAll(setupTestcontainers)

test('open codeserver', async ({codeServer, page}) => {
  await page.goto(codeServer.url)

  await codeServer.isEditorVisible()
})

test('wait for welcome screen to load', async ({codeServer, page}, testInfo) => {
  await page.goto(codeServer.url);

  await codeServer.isEditorVisible()
  page.on("console", console.log)

  await codeServer.isEditorVisible()
  await utils.waitForStableDOM(page, "div.monaco-workbench", 1000, 10000)
  await utils.waitForNextRender(page)

  await utils.takeScreenshot(page, testInfo, "welcome.png")
})

test('use the terminal to run command', async ({codeServer, page}, testInfo) => {
  await page.goto(codeServer.url);

  await test.step("Should always see the code-server editor", async () => {
    expect(await codeServer.isEditorVisible()).toBe(true)
  })

  await test.step("should show the Integrated Terminal", async () => {
    await codeServer.focusTerminal()
    expect(await page.isVisible("#terminal")).toBe(true)
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
