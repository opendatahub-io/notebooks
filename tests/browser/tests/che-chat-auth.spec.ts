import { expect, test } from '@playwright/test';

import { setupTestcontainers } from './testcontainers';
import { CodeServer } from './models/codeserver';
import { GenericContainer } from 'testcontainers';
import { HttpWaitStrategy } from 'testcontainers/build/wait-strategies/http-wait-strategy.js';

test.beforeAll(setupTestcontainers);

test('starts the GitHub device flow from Che Code chat', async ({ page }) => {
  test.setTimeout(180_000);

  const url = process.env['CHECODE_URL'];
  const image = process.env['TEST_TARGET'];
  test.skip(!url && !image, 'Set CHECODE_URL or TEST_TARGET');

  const container = url ? undefined : await new GenericContainer(image!)
    .withExposedPorts(8888)
    .withWaitStrategy(new HttpWaitStrategy('/', 8888, { abortOnContainerExit: true }))
    .start();

  try {
    const codeServer = new CodeServer(
      page,
      url ?? `http://${container!.getHost()}:${container!.getMappedPort(8888)}`,
    );
    await page.goto(codeServer.url, { waitUntil: 'domcontentloaded', timeout: 60_000 });
    await expect(page.locator('.monaco-workbench')).toBeVisible({ timeout: 15_000 });

    const chatInput = page.getByRole('textbox', { name: /Chat Input/ });
    // The chat editor is a Monaco contenteditable. A transient editor layer can
    // intercept a mouse click even after the textbox is actionable; focus and
    // type through the keyboard instead.
    await chatInput.focus();
    await page.keyboard.type('hi');
    await chatInput.press('Enter');

    await page.getByRole('button', { name: 'Continue with GitHub' }).click();

    await expect(page.getByRole('dialog', { name: /Your Code:/ })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('dialog', { name: /Your Code:/ })).toContainText(/[A-Z0-9]{3,5}-[A-Z0-9]{3,5}/i);

    // This action both copies the code and starts the extension's polling flow.
    // Opening github.com manually would not start device-code polling.
    await page.getByRole('button', { name: 'Copy & Continue to Browser' }).click();

    const externalSiteDialog = page.getByRole('dialog', {
      name: /open the external website/i,
    });
    await expect(externalSiteDialog).toBeVisible({ timeout: 15_000 });
    await expect(externalSiteDialog).toContainText(/github\.com\/login\/device/);
    await externalSiteDialog.getByRole('button', { name: 'Open' }).click();
  } finally {
    await container?.stop();
  }
});
