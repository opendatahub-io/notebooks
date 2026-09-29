import { expect, test as baseTest } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import * as fs from 'node:fs/promises';
import { GenericContainer } from 'testcontainers';
import { HttpWaitStrategy } from 'testcontainers/build/wait-strategies/http-wait-strategy.js';
import { DEFAULT_JUPYTER_TEST_IMAGE } from '../playwright.config';
import { JupyterLab } from './models/jupyterlab';
import { setupTestcontainers } from './testcontainers';

const TERMINAL_VALUE = 'offline-terminal-file-content';
const ENV_VALUE = process.env['OFFLINE_FAKE_VALUE'] ?? 'offline-browser-fixture';
const GIT_REPOSITORY = 'offline-git-repo';
const GIT_FILE = 'git-ui.txt';

type JupyterFixtures = {
  jupyterBaseURL: string;
};

const test = baseTest.extend<Record<never, never>, JupyterFixtures>({
  jupyterBaseURL: [async ({}, use) => {
    const configuredBaseURL = process.env['OFFLINE_BASE_URL'];
    if (configuredBaseURL) {
      await use(configuredBaseURL);
      return;
    }

    const image = process.env['TEST_TARGET'] ?? DEFAULT_JUPYTER_TEST_IMAGE;

    const container = await new GenericContainer(image)
      .withEnvironment({
        HOME: '/opt/app-root/src',
        NOTEBOOK_ROOT_DIR: '/opt/app-root/src',
        NOTEBOOK_BASE_URL: '/notebook/offline/',
        NOTEBOOK_ARGS: '--ServerApp.port=8888\n--ServerApp.token=\'\'\n--ServerApp.password=\'\'\n--ServerApp.quit_button=False',
        OFFLINE_FAKE_VALUE: ENV_VALUE,
      })
      .withExposedPorts(8888)
      .withWaitStrategy(new HttpWaitStrategy('/notebook/offline/api', 8888, { abortOnContainerExit: true }))
      .start();

    try {
      const fixture = await container.exec([
        'bash',
        '-lc',
        [
          'set -Eeuo pipefail',
          'git config --global user.name "Offline Browser Fixture"',
          'git config --global user.email "offline-browser@example.invalid"',
          'mkdir -p /opt/app-root/src/offline-git-remote.git /opt/app-root/src/offline-git-repo',
          'git -C /opt/app-root/src/offline-git-remote.git init --bare',
          'git -C /opt/app-root/src/offline-git-repo init',
          'printf "%s\\n" "initial content" > /opt/app-root/src/offline-git-repo/git-ui.txt',
          'git -C /opt/app-root/src/offline-git-repo add git-ui.txt',
          'git -C /opt/app-root/src/offline-git-repo commit -m "initial offline fixture"',
          'git -C /opt/app-root/src/offline-git-repo remote add origin file:///opt/app-root/src/offline-git-remote.git',
        ].join('; '),
      ]);
      if (fixture.exitCode !== 0) {
        throw new Error(`Could not prepare JupyterLab Git fixture: ${fixture.output}`);
      }

      await use(`http://${container.getHost()}:${container.getMappedPort(8888)}/notebook/offline/`);
    } finally {
      await container.stop();
    }
  }, { scope: 'worker' }],
});

test.beforeAll(setupTestcontainers);

test.describe('JupyterLab offline features', { tag: ['@jupyter', '@offline', '@tier1'] }, () => {

  test.describe.configure({ timeout: 120_000 });

  test('creates, runs, renames, saves, closes, and reopens a notebook', async ({ page, jupyterBaseURL }, testInfo) => {
    const id = randomUUID();
    const initialNotebookName = `offline-lifecycle-${id}.ipynb`;
    const notebookName = `offline-lifecycle-renamed-${id}.ipynb`;
    const source = 'print(1 + 1)';
    const expectedOutput = '2';
    const lab = await JupyterLab.open(page, testInfo, jupyterBaseURL);
    const launcher = await lab.openLauncher();
    const draft = await launcher.newNotebook();
    const cell = await draft.cells.first().run(source);
    await expect(cell.output).toHaveText(expectedOutput, { timeout: 30_000 });

    const saved = await draft.saveAs(initialNotebookName);
    const renamed = await saved.rename(notebookName);
    await renamed.save();
    const files = await renamed.close();
    const reopened = await files.openNotebook(notebookName);
    await expect(reopened.cells.first().output).toHaveText(expectedOutput);
    await expect(reopened.cells.first().source).toHaveText(source);
  });

  test('uploads and executes a notebook through the file chooser', async ({ page, jupyterBaseURL }, testInfo) => {
    const lab = await JupyterLab.open(page, testInfo, jupyterBaseURL);
    const uploadName = `offline-upload-${randomUUID()}.ipynb`;
    const uploadPath = testInfo.outputPath(uploadName);
    await fs.writeFile(uploadPath, JSON.stringify({
      cells: [
        {
          cell_type: 'code',
          id: `cell-${randomUUID()}`,
          execution_count: null,
          metadata: {},
          outputs: [],
          source: ["print(f'offline upload output: {6 * 7}')\n"],
        },
      ],
      metadata: {
        kernelspec: { display_name: 'Python 3 (ipykernel)', language: 'python', name: 'python3' },
        language_info: { name: 'python', version: '3.12.0' },
      },
      nbformat: 4,
      nbformat_minor: 5,
    }));

    const notebook = await lab.files.uploadNotebook(uploadPath);
    const cell = await notebook.cells.first().run();
    await expect(cell.output).toContainText('offline upload output: 42', { timeout: 30_000 });
  });

  test('runs a terminal command with the injected environment and verifies its file in the browser', async ({ page, jupyterBaseURL }, testInfo) => {
    const terminalFile = `offline-terminal-file-${randomUUID()}.txt`;
    const completionMarker = `COMMAND_DONE=${randomUUID()}`;
    const lab = await JupyterLab.open(page, testInfo, jupyterBaseURL);
    const launcher = await lab.openLauncher();
    const terminal = await launcher.newTerminal();
    await terminal.run(
      `printf 'OFFLINE_ENV=%s\\n' "$OFFLINE_FAKE_VALUE" > '${terminalFile}'; printf '%s\\n' '${TERMINAL_VALUE}' >> '${terminalFile}'; printf '%s\\n' '${completionMarker}' >> '${terminalFile}'`,
    );

    const files = await terminal.openFiles();
    await files.refresh();
    const editor = await files.openText(terminalFile);
    await expect(editor.content).toContainText(`OFFLINE_ENV=${ENV_VALUE}`);
    await expect(editor.content).toContainText(TERMINAL_VALUE);
    await expect(editor.content).toContainText(completionMarker);
  });

  test('uses the JupyterLab Git UI to stage, commit, and inspect a local repository change', async ({ page, jupyterBaseURL }, testInfo) => {
    const id = randomUUID();
    const commitMessage = `offline browser UI commit ${id}`;
    const lab = await JupyterLab.open(page, testInfo, jupyterBaseURL);
    const editor = await lab.files.openText(`${GIT_REPOSITORY}/${GIT_FILE}`);
    await editor.replace(`edited through the JupyterLab Git workflow ${id}`);
    await editor.save();

    const changes = await editor.openGit(`/opt/app-root/src/${GIT_REPOSITORY}`);
    const staged = await changes.stage(GIT_FILE);
    const history = await staged.commit(commitMessage);
    await expect(history.entry(commitMessage)).toBeVisible();
  });
});
