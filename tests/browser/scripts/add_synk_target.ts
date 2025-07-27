#!/usr/bin/env -S node --no-warnings
// #!/usr/bin/env -S node --no-warnings --loader ts-node/esm
import {chromium} from 'playwright';
import type {BrowserContext, Page} from 'playwright';

// TODO: log-in at https://app.snyk.io/org/red-hat-openshift-data-science-rhods/projects
// TODO: then modify these values before running
const BRANCH = 'rhoai-2.22';
// $ find . -name Pipfile -exec echo \'{}\', \;
const PIPFILES = [
    './runtimes/rocm-tensorflow/ubi9-python-3.11/Pipfile',
    './runtimes/rocm-pytorch/ubi9-python-3.11/Pipfile',
    // TODO: ...
];

async function main() {
    const browser = await chromium.connectOverCDP("http://localhost:9222");
    const context = browser.contexts()[0];

    const page = await findVisiblePage(context);
    for (const pipfile of PIPFILES) {
        const target = pipfile.replace(/^\./, "");
        console.log(" - processing " + target);
        await addPipfile(page, target, BRANCH);
    }

    await page.waitForTimeout(10 * 1000);

    await context.close();
    await browser.close();
}

async function findVisiblePage(context: BrowserContext) : Promise<Page> {
    return context.pages().filter(async page => await page.evaluate(() => document.visibilityState) === 'visible')[0];
}

async function addPipfile(page: Page, target: string, branch: string) {
    const url = 'https://app.snyk.io/org/red-hat-openshift-data-science-rhods/sources/9a3e5d90-b782-468a-a042-9a2073736f0b/add'
    try {
        await page.goto(url);
    } catch (error) {
        // seen the following error once, but navigation succeeded,
        // it cleared up when I restarted browser, but let's tolerate it
        // > page.goto: net::ERR_ABORTED
        console.log(error);
    }
    await page.waitForURL(url);

    const searchField = page.getByLabel('Search');
    await searchField.fill('red-hat-data-services/notebooks');
    await searchField.press('Enter');

    const repoCheckbox = page.locator('xpath=//label[@data-snyk-test="repo label"][@title="notebooks"]')
    await repoCheckbox.check();

    const repoDropdown = page.getByLabel('Select a repository');
    await repoDropdown.selectOption('red-hat-data-services/notebooks');

    const targetField = page.getByLabel('Target');
    await targetField.fill(target);

    const branchField = page.getByLabel('Branch');
    await branchField.fill(branch);

    await page.getByRole('button', {name: 'Add selected repositories'}).click();
    await page.waitForURL('https://app.snyk.io/org/red-hat-openshift-data-science-rhods/import-logs');
}

(async () => {
    await main();
})();
