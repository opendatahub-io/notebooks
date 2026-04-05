import {Page, TestInfo} from "@playwright/test";

export async function waitForStableDOM(page: Page, pageRootSelector: string, checkPeriod: number, timeout: number): Promise<void> {
    // https://github.com/cypress-io/cypress/issues/5275#issuecomment-1003669708
    const parameters: [string, number, number] = [pageRootSelector, checkPeriod, timeout]
    await page.evaluate( ([pageRootSelector, checkPeriod, timeout]) => {
        const targetNode = document.querySelector(pageRootSelector);
        if (!targetNode) {
            throw new Error(`Selector "${pageRootSelector}" did not match any element`);
        }
        const config = { attributes: true, childList: true, subtree: true };

        const started = performance.now();
        let mutated = started;

        const callback: MutationCallback = (mutationList, _observer) => {
            for (const mutation of mutationList) {
                mutated = performance.now()

                if (mutation.type === "childList") {
                    console.log("A child node has been added or removed.");
                } else if (mutation.type === "attributes") {
                    console.log(`The ${mutation.attributeName} attribute was modified.`);
                }
            }
        };

        const observer = new MutationObserver(callback);
        observer.observe(targetNode, config);

        return new Promise<void>((resolve, reject) => {
            const loop = () => {
                const now = performance.now();
                if (now - mutated > checkPeriod) {
                    observer.disconnect();
                    resolve();
                    return;
                }
                if (now - started > timeout) {
                    observer.disconnect();
                    reject(new Error(`DOM not stable after ${timeout}ms`));
                    return;
                }
                window.setTimeout(loop, checkPeriod);
            };
            loop()
        })
    }, parameters);
}

export async function waitForNextRender(page: Page) {
    /**
     * https://webperf.tips/tip/react-hook-paint/
     *
     * alternative implementation, send yourself a message
     *
     * function runAfterFramePaint(callback) {
     *     requestAnimationFrame(() => {
     *         const messageChannel = new MessageChannel();
     *
     *         messageChannel.port1.onmessage = callback;
     *         messageChannel.port2.postMessage(undefined);
     *     });
     * }
     */
    // wait for next frame being rendered
    await page.evaluate( () => {
        return new window.Promise<void>((resolve) => {
            window.requestAnimationFrame(() => window.setTimeout(resolve));
        });
    });
}

// https://github.com/microsoft/playwright/issues/14854#issuecomment-1155347129
export async function screenshotOnFailure({ page }: { page: Page }, testInfo: TestInfo) {
    if (testInfo.status !== testInfo.expectedStatus) {
        await takeScreenshot(page, testInfo, `failure.png`)
    }
}

export async function takeScreenshot(page: Page, testInfo: TestInfo, filename: string) {
    // Get a unique place for the screenshot.
    const screenshotPath = testInfo.outputPath(filename);
    // Add it to the report.
    testInfo.attachments.push({name: 'screenshot', path: screenshotPath, contentType: 'image/png'});
    // Take the screenshot itself.
    await page.screenshot({path: screenshotPath, timeout: 5000});
}
