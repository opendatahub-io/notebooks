import type { Locator, Page } from '@playwright/test';

/** JupyterLab's DOM contract. Keep CSS and accessible-name knowledge here. */
export function jupyterLabSelectors(page: Page) {
  const dialog = (text: RegExp) => page.getByRole('dialog').filter({ hasText: text }).last();
  const git = page.locator('#GitSession-root, #jp-git-sessions').first();
  return {
    shell: page.locator('.jp-LabShell'),
    sidebar: page.locator('.jp-SideBar').first(),
    tab: (name: string) => page.getByRole('tab', { name, exact: true }).last(),
    closeTab: (tab: Locator) => tab.locator('.lm-TabBar-tabCloseIcon'),
    launcher: {
      panel: page.locator('.jp-Launcher').last(),
      open: page.getByRole('button', { name: 'New Launcher' }).first(),
      python: page.locator('.jp-Launcher').last().getByText(/Python 3/i).first(),
      terminal: page.locator('.jp-Launcher').last().getByText('Terminal', { exact: true }),
    },
    files: {
      tab: page.getByRole('tab', { name: /^File Browser/ }).first(),
      row: (name: string) => page.locator('.jp-DirListing-itemText').getByText(name, { exact: true }).first(),
      upload: page.getByRole('button', { name: 'Upload Files', exact: true }).first(),
      refresh: page.getByRole('button', { name: 'Refresh the file browser.', exact: true }).first(),
    },
    notebook: (name?: string) => name === undefined
      ? page.locator('.jp-NotebookPanel').last()
      : page.getByRole('tabpanel', { name, exact: true }),
    cells: (panel: Locator) => panel.locator('.jp-CodeCell'),
    cell: (cell: Locator) => ({
      editor: cell.locator('.cm-content').first(),
      output: cell.locator('.jp-OutputArea-output'),
    }),
    textEditor: (name: string) => page.getByRole('tabpanel', { name, exact: true }).locator('.cm-content').first(),
    terminal: page.locator('.jp-Terminal').last(),
    menu: {
      file: page.getByRole('menuitem', { name: 'File', exact: true }),
      save: page.getByRole('menuitem', { name: /^Save (Notebook|Text)(?: Ctrl\+S)?$/ }).first(),
      rename: page.locator('.lm-Menu-itemLabel').filter({ hasText: /^Rename/ }).first()
        .locator('xpath=ancestor::*[@role="menuitem"][1]'),
    },
    dialogs: {
      kale: dialog(/You can find more information under \/opt\/app-root\/src\/kale\.log/),
      saveAs: dialog(/Save File As|Rename file/),
      rename: dialog(/Rename File/i),
      untitled: dialog(/Save changes in "Untitled\.ipynb"/),
      repository: page.getByRole('dialog').last(),
      input: (root: Locator) => root.locator('input').first(),
      close: (root: Locator) => root.getByRole('button', { name: /Close|OK/i }).last(),
      save: (root: Locator) => root.getByRole('button', { name: /Save|Rename and Save/i }).last(),
      renameFile: (root: Locator) => root.getByRole('button', { name: /Rename/i }).last(),
      discard: (root: Locator) => root.getByRole('button', { name: 'Discard', exact: true }),
      open: (root: Locator) => root.getByRole('button', { name: /Open/i }).last(),
    },
    git: {
      tab: page.getByRole('tab', { name: 'Git', exact: true }).first(),
      panel: git,
      openRepository: git.getByRole('button', { name: /Open (a )?repository/i }).first(),
      // Escape data as a CSS string, rather than interpreting filenames as selectors.
      changedFile: (name: string) => git.locator(`[title^=${JSON.stringify(`${name} •`)}]`).first(),
      stage: (row: Locator) => row.getByRole('button', { name: 'Stage this change', exact: true }),
      summary: git.locator('.jp-git-CommitBox input[placeholder^="Summary"]').first(),
      commit: git.getByRole('button', { name: /^Commit$/i }).first(),
      history: git.getByRole('heading', { name: 'History Section', exact: true }),
      commitEntry: (message: string) => git.getByRole('listitem').filter({ hasText: message }).first(),
    },
  };
}
