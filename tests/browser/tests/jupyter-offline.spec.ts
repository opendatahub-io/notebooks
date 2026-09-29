import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import * as fs from 'node:fs/promises';
import { JupyterLab } from './models/jupyterlab';

const TERMINAL_VALUE = 'offline-terminal-file-content';
const ENV_VALUE = process.env['OFFLINE_FAKE_VALUE'] ?? 'offline-browser-fixture';
const GIT_REPOSITORY = 'offline-git-repo';
const GIT_FILE = 'git-ui.txt';

test.describe('JupyterLab offline features', { tag: ['@jupyter', '@offline', '@tier1'] }, () => {
  test('creates, runs, renames, saves, closes, and reopens a notebook', async ({ page }, testInfo) => {
    const id = randomUUID();
    const initialNotebookName = `offline-lifecycle-${id}.ipynb`;
    const notebookName = `offline-lifecycle-renamed-${id}.ipynb`;
    const source = 'print(1 + 1)';
    const expectedOutput = '2';
    const lab = await JupyterLab.open(page, testInfo);
    const launcher = await lab.openLauncher();
    const draft = await launcher.newNotebook();
    const cell = await draft.cells.first().run(source);
    await expect(cell.output).toHaveText(expectedOutput);

    const saved = await draft.saveAs(initialNotebookName);
    const renamed = await saved.rename(notebookName);
    await renamed.save();
    const files = await renamed.close();
    const reopened = await files.openNotebook(notebookName);
    await expect(reopened.cells.first().output).toHaveText(expectedOutput);
    await expect(reopened.cells.first().source).toHaveText(source);
  });

  test('uploads and executes a notebook through the file chooser', async ({ page }, testInfo) => {
    const lab = await JupyterLab.open(page, testInfo);
    const uploadName = `offline-upload-${randomUUID()}.ipynb`;
    const uploadPath = testInfo.outputPath(uploadName);
    await fs.writeFile(uploadPath, JSON.stringify({
      cells: [
        {
          cell_type: 'code',
          execution_count: null,
          metadata: {},
          outputs: [],
          source: ["print('offline upload output')\n"],
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
    await expect(cell.output).toContainText('offline upload output');
  });

  test('runs a terminal command with the injected environment and verifies its file in the browser', async ({ page }, testInfo) => {
    const terminalFile = `offline-terminal-file-${randomUUID()}.txt`;
    const lab = await JupyterLab.open(page, testInfo);
    const launcher = await lab.openLauncher();
    const terminal = await launcher.newTerminal();
    await terminal.run(
      `printf 'OFFLINE_ENV=%s\\n' "$OFFLINE_FAKE_VALUE" > '${terminalFile}'; printf '%s\\n' '${TERMINAL_VALUE}' >> '${terminalFile}'`,
    );

    const files = await terminal.openFiles();
    await files.refresh();
    const editor = await files.openText(terminalFile);
    await expect(editor.content).toContainText(`OFFLINE_ENV=${ENV_VALUE}`);
    await expect(editor.content).toContainText(TERMINAL_VALUE);
  });

  test('uses the JupyterLab Git UI to stage, commit, and inspect a local repository change', async ({ page }, testInfo) => {
    const id = randomUUID();
    const commitMessage = `offline browser UI commit ${id}`;
    const lab = await JupyterLab.open(page, testInfo);
    const editor = await lab.files.openText(`${GIT_REPOSITORY}/${GIT_FILE}`);
    await editor.replace(`edited through the JupyterLab Git workflow ${id}`);
    await editor.save();

    const changes = await editor.openGit(`/opt/app-root/src/${GIT_REPOSITORY}`);
    const staged = await changes.stage(GIT_FILE);
    const history = await staged.commit(commitMessage);
    await expect(history.entry(commitMessage)).toBeVisible();
  });
});
