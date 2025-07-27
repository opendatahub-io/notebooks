#!/usr/bin/env -S node
// #!/usr/bin/env -S node --no-warnings --loader ts-node/esm
import {chromium} from 'playwright';
import type {Browser, Page} from "@playwright/test";

async function main() {
    // https://playwright.dev/docs/browsers#google-chrome--microsoft-edge
    const browserServer = await chromium.launchServer({
        channel: 'chrome',
        headless: false,
        chromiumSandbox: false,
        // https://github.com/microsoft/playwright/blob/2a445bb005b4671e03697ce13e7070d1930d1186/packages/playwright-core/src/server/chromium/chromiumSwitches.ts
        // https://github.com/microsoft/playwright/blob/2a445bb005b4671e03697ce13e7070d1930d1186/packages/playwright-core/src/server/chromium/chromium.ts#L299
        args: [
            '--ignore-certificate-errors',
            '--remote-debugging-port=9222',
        ]
    });

    console.log("Browser server listening on:\n " + browserServer.wsEndpoint());
    console.log("CDP socket listening on:\n localhost:9222\n");

    // NOTE: unless we open a page, the browser will not materialize its window

    // NOTE: we cannot use the regular `context.newPage()`, because it will force the focus emulation.
    // Focus emulation means that every tab reports as visible and taking over from the manual user then does not work.
    // - https://github.com/microsoft/playwright/issues/3570#issuecomment-3038913499
    // - https://github.com/microsoft/playwright/blob/6c8c0db530ee44c2ce44a3f26f3daeebccce18a2/packages/playwright-core/src/server/chromium/crPage.ts
    // The following command is supposed to disable it again, but it did nothing for me.
    // await session.send('Emulation.setFocusEmulationEnabled', {enabled: false});

    // NOTE: connection method does not really matter, either of them works
    const browser = await chromium.connect(browserServer.wsEndpoint());
    // const browser = await chromium.connectOverCDP('http://localhost:9222');

    const session = await browser.newBrowserCDPSession();
    // https://stackoverflow.com/questions/68000609/target-domain-events-not-firing
    // https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-setDiscoverTargets
    await session.send('Target.setDiscoverTargets', {discover: true});
    const targetCreated = new Promise((resolve) => {
        session.on('Target.targetCreated', resolve);
    });
    await session.send('Target.createTarget', {
        url: 'about:blank',
    });
    await targetCreated;
    console.log(`\nSuccessfully captured newly created target`);

    const page = await getFirstPage(browser);
    await page.bringToFront();
    console.log(`\nSuccessfully captured page: ${page}`);
}

/**
 * Playwright is a bit delayed before it notices the new page.
 * Needs a retry with a timeout.
 */
async function getFirstPage(browser: Browser): Promise<Page> {
    const timeout = 5 * 1000;
    const started = Date.now();

    let page: Page = undefined;
    while ((page === null || page === undefined) && Date.now() - started < timeout) {
        const context = browser.contexts()[0];
        page = context?.pages()[0];
        if (page !== null && page !== undefined) {
            return page;
        }
        await new Promise(r => setTimeout(r, 100));
    }
    throw new Error(`Could not get first page within ${timeout}ms`);
}

(async () => {
    await main()
})();
