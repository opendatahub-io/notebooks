import { expect, type Locator, type Page, type TestInfo } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { basename } from 'node:path';
import { jupyterLabSelectors } from './selectors';
import { chainable, type Chain } from './chain';

/** Shared interaction plumbing; workflows use the typed views below. */
class LabSession {
  readonly ui;

  constructor(readonly page: Page, private readonly testInfo: TestInfo) {
    this.ui = jupyterLabSelectors(page);
  }

  async dismissOfflineServiceError(): Promise<void> {
    const { dialogs } = this.ui;
    await dialogs.kale.waitFor({ state: 'visible', timeout: 5_000 }).catch(() => undefined);
    if (await dialogs.kale.isVisible()) {
      if (!this.testInfo.annotations.some(({ type }) => type === 'known-offline-service-error')) {
        this.testInfo.annotations.push({
          type: 'known-offline-service-error',
          description: 'Kale attempted its optional localhost:80 service and was dismissed; core JupyterLab UI remains under test.',
        });
      }
      // This exact known modal can appear over another Jupyter dialog.
      await dialogs.close(dialogs.kale).click({ force: true });
      await expect(dialogs.kale).toBeHidden({ timeout: 5_000 });
    }
  }

  async saveMenu(): Promise<void> {
    await this.dismissOfflineServiceError();
    await this.ui.menu.file.click();
    await this.ui.menu.save.click({ timeout: 15_000 });
  }

  async saveAsMenu(): Promise<void> {
    await this.dismissOfflineServiceError();
    await this.ui.menu.file.click();
    await this.ui.menu.saveAs.click({ timeout: 15_000 });
  }

  async save(action: () => Promise<void>): Promise<void> {
    const responsePromise = this.page.waitForResponse(
      (response) => response.request().method() === 'PUT' && /\/api\/contents\//.test(response.url()),
      { timeout: 30_000 },
    );
    try {
      await action();
    } catch (error) {
      await responsePromise.catch(() => undefined);
      throw error;
    }
    const response = await responsePromise;
    expect(response.ok()).toBe(true);
  }

  async openFiles(): Promise<FileBrowser> {
    // Clicking the selected sidebar tab collapses it in JupyterLab.
    if ((await this.ui.files.tab.getAttribute('aria-selected')) !== 'true') {
      await this.ui.files.tab.click();
    }
    await expect(this.ui.files.upload).toBeVisible();
    return new FileBrowser(this);
  }
}

export class JupyterLab {
  readonly files: FileBrowser;

  private constructor(private readonly session: LabSession) {
    this.files = new FileBrowser(session);
  }

  static readonly open: (page: Page, testInfo: TestInfo, baseURL?: string) => Chain<JupyterLab> = chainable(
    async (page: Page, testInfo: TestInfo, baseURL?: string): Promise<JupyterLab> => {
      const session = new LabSession(page, testInfo);
      const workspace = `offline-${randomUUID()}`;
      const workspaceURL = baseURL
        ? `${baseURL}lab/workspaces/${workspace}?reset`
        : `./lab/workspaces/${workspace}?reset`;
      await page.goto(workspaceURL);
      await expect(session.ui.shell).toBeVisible({ timeout: 120_000 });
      await expect(session.ui.sidebar).toBeVisible();
      await session.dismissOfflineServiceError();
      return new JupyterLab(session);
    },
  );

  async openLauncher(): Promise<Launcher> {
    const { launcher } = this.session.ui;
    if (!(await launcher.panel.isVisible())) {
      await launcher.open.click();
    }
    await expect(launcher.panel).toBeVisible();
    return new Launcher(this.session);
  }
}

export class Launcher {
  constructor(private readonly session: LabSession) {}

  async newNotebook(): Promise<DraftNotebook> {
    await this.session.ui.launcher.python.click();
    const notebook = new DraftNotebook(this.session);
    await expect(notebook.panel).toBeVisible();
    await expect(notebook.cells.first().source).toBeVisible();
    return notebook;
  }

  async newTerminal(): Promise<Terminal> {
    await this.session.ui.launcher.terminal.click();
    await expect(this.session.ui.terminal).toBeVisible();
    return new Terminal(this.session);
  }
}

export class FileBrowser {
  constructor(private readonly session: LabSession) {}

  async refresh(): Promise<this> {
    await this.session.ui.files.refresh.click();
    return this;
  }

  private async open(path: string): Promise<void> {
    for (const part of path.split('/')) {
      const row = this.session.ui.files.row(part);
      await expect(row).toBeVisible({ timeout: 30_000 });
      await row.dblclick();
    }
  }

  async openNotebook(path: string): Promise<SavedNotebook> {
    await this.open(path);
    const notebook = new SavedNotebook(this.session, basename(path));
    await expect(notebook.panel).toBeVisible();
    return notebook;
  }

  async uploadNotebook(path: string): Promise<SavedNotebook> {
    const chooser = this.session.page.waitForEvent('filechooser');
    await this.session.ui.files.upload.click();
    await (await chooser).setFiles(path);
    const name = basename(path);
    // JupyterLab versions differ in whether upload also opens the document.
    const tab = this.session.ui.tab(name);
    if (await tab.isVisible()) {
      await tab.click();
    } else {
      await this.open(name);
    }
    const notebook = new SavedNotebook(this.session, name);
    await expect(notebook.panel).toBeVisible();
    return notebook;
  }

  async openText(path: string): Promise<TextEditor> {
    await this.open(path);
    const editor = new TextEditor(this.session, basename(path));
    await expect(editor.content).toBeVisible();
    return editor;
  }
}

class Notebook {
  readonly cells;

  constructor(protected readonly session: LabSession, readonly panel: Locator) {
    const cells = session.ui.cells(panel);
    this.cells = {
      first: () => new NotebookCell(session, cells.first()),
      at: (index: number) => new NotebookCell(session, cells.nth(index)),
    };
  }
}

export class NotebookCell {
  readonly source: Locator;
  readonly output: Locator;

  constructor(private readonly session: LabSession, cell: Locator) {
    const ui = session.ui.cell(cell);
    this.source = ui.editor;
    this.output = ui.output;
  }

  async run(source?: string): Promise<this> {
    await this.session.dismissOfflineServiceError();
    await this.source.click();
    if (source !== undefined) {
      await this.source.fill(source);
    }
    await this.source.press('Shift+Enter');
    return this;
  }
}

/** First save needs a name; rename/close are exposed only on SavedNotebook. */
export class DraftNotebook extends Notebook {
  constructor(session: LabSession) {
    super(session, session.ui.notebook());
  }

  async saveAs(name: string): Promise<SavedNotebook> {
    const { dialogs } = this.session.ui;
    await this.session.saveAsMenu();
    await expect(dialogs.saveAs).toBeVisible();
    await dialogs.input(dialogs.saveAs).fill(name);
    await this.session.save(() => dialogs.save(dialogs.saveAs).click());
    if (await dialogs.untitled.isVisible()) {
      await dialogs.discard(dialogs.untitled).click({ force: true });
      await expect(dialogs.untitled).toBeHidden({ timeout: 15_000 });
    }
    const saved = new SavedNotebook(this.session, name);
    await expect(saved.panel).toBeVisible();
    return saved;
  }
}

export class SavedNotebook extends Notebook {
  constructor(session: LabSession, readonly name: string) {
    super(session, session.ui.notebook(name));
  }

  async rename(name: string): Promise<SavedNotebook> {
    await this.session.ui.tab(this.name).click();
    const { menu, dialogs } = this.session.ui;
    await menu.file.click();
    await menu.rename.click();
    await expect(dialogs.rename).toBeVisible();
    await dialogs.input(dialogs.rename).fill(name);
    await dialogs.renameFile(dialogs.rename).click();
    const renamed = new SavedNotebook(this.session, name);
    await expect(renamed.panel).toBeVisible();
    return renamed;
  }

  async save(): Promise<this> {
    await this.session.ui.tab(this.name).click();
    await this.session.save(() => this.session.saveMenu());
    return this;
  }

  async close(): Promise<FileBrowser> {
    const tab = this.session.ui.tab(this.name);
    await this.session.ui.closeTab(tab).click();
    await expect(this.panel).toBeHidden();
    return this.session.openFiles();
  }
}

export class Terminal {
  constructor(private readonly session: LabSession) {}

  /**
   * JupyterLab renders xterm output through a canvas-backed surface, so its
   * ordinary DOM container does not expose command output reliably to Playwright.
   * Workflows should write a unique completion marker to a file and assert it
   * through the file browser. JupyterLab's terminal accessibility mode is an
   * alternative when the terminal's rendered output itself is under test.
   */
  async run(command: string): Promise<this> {
    await this.session.ui.terminal.click();
    await this.session.page.keyboard.type(command);
    await this.session.page.keyboard.press('Enter');
    return this;
  }

  async openFiles(): Promise<FileBrowser> {
    return this.session.openFiles();
  }
}

export class TextEditor {
  readonly content: Locator;

  constructor(private readonly session: LabSession, readonly name: string) {
    this.content = session.ui.textEditor(name);
  }

  async replace(content: string): Promise<this> {
    await this.content.fill(content);
    return this;
  }

  async save(): Promise<this> {
    await this.session.ui.tab(this.name).click();
    await this.session.save(() => this.session.saveMenu());
    return this;
  }

  async openGit(repositoryPath: string): Promise<GitChanges> {
    const { git, dialogs } = this.session.ui;
    await git.tab.click();
    await expect(git.panel).toBeVisible({ timeout: 30_000 });
    if (await git.openRepository.isVisible()) {
      await git.openRepository.click();
      await dialogs.input(dialogs.repository).fill(repositoryPath);
      await dialogs.open(dialogs.repository).click();
    }
    return new GitChanges(this.session);
  }
}

export class GitChanges {
  constructor(private readonly session: LabSession) {}

  async stage(name: string): Promise<StagedChanges> {
    const { git } = this.session.ui;
    const row = git.changedFile(name);
    await expect(row).toBeVisible();
    await row.hover();
    await git.stage(row).click();
    return new StagedChanges(this.session);
  }
}

export class StagedChanges {
  constructor(private readonly session: LabSession) {}

  async commit(message: string): Promise<GitHistory> {
    const { git } = this.session.ui;
    await git.summary.fill(message);
    await expect(git.commit).toBeEnabled();
    await git.commit.click();
    await expect(git.history).toBeVisible();
    return new GitHistory(this.session);
  }
}

export class GitHistory {
  constructor(private readonly session: LabSession) {}

  entry(message: string): Locator {
    return this.session.ui.git.commitEntry(message);
  }
}
